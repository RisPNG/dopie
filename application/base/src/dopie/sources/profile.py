from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from dopie.paths import AppPaths
from dopie.security.vault import VaultStore
from dopie.storage import SettingsStore, SourceStore


class PortableProfileService:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def export_portable_profile(
        self,
        destination: Path,
        password: str | None = None,
    ) -> None:
        private_sources = self.paths.vault.exists()
        manifest = {
            "format": "dopie-portable-profile",
            "version": 2,
            "private_sources": private_sources,
            "requires_password": private_sources and bool(password),
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("profile.json", json.dumps(manifest, indent=2))
            archive.writestr(
                "data/sources.json",
                self.paths.sources.read_text(encoding="utf-8") if self.paths.sources.exists() else "[]",
            )
            if private_sources:
                archive.writestr(
                    "data/source-vault.dopie",
                    VaultStore(self.paths.vault, self.paths.vault_key).export_for_transfer(password or ""),
                )
            settings = SettingsStore(self.paths.settings).load()
            portable_settings = {
                key: settings[key]
                for key in (
                    "theme",
                    "include_available_in_library",
                    "check_updates_on_launch",
                    "application_update_source",
                )
            }
            archive.writestr("data/preferences.json", json.dumps(portable_settings, indent=2))

    def export_portable_copy(
        self,
        destination: Path,
        target_platform: str,
        password: str | None = None,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="dopie-export-", dir=self.paths.data) as temporary:
            profile = Path(temporary) / "DoPie.dopie-profile"
            self.export_portable_profile(profile, password=password)
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(profile, "DoPie/provisioning/DoPie.dopie-profile")
                launchers = {
                    "linux": ("start-dopie.sh",),
                    "windows": ("Start DoPie.vbs",),
                    "both": ("start-dopie.sh", "Start DoPie.vbs"),
                }[target_platform]
                for name in ("THIRD_PARTY_NOTICES.md", *launchers):
                    path = self.paths.project / name
                    if path.exists():
                        archive.write(path, Path("DoPie") / name)
                for name in ("pyproject.toml", "requirements.lock"):
                    path = self.paths.active_project / name
                    if path.exists():
                        archive.write(path, Path("DoPie/application/base") / name)
                for name in ("assets", "changelog", "docs", "slices", "src"):
                    root = self.paths.active_project / name
                    if not root.exists():
                        continue
                    for path in root.rglob("*"):
                        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                            continue
                        archive.write(
                            path,
                            Path("DoPie/application/base") / path.relative_to(self.paths.active_project),
                        )
                root = self.paths.project / "bootstrap"
                if root.exists():
                    for path in root.rglob("*"):
                        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                            continue
                        if path.name == "Start DoPie.ps1" and target_platform == "linux":
                            continue
                        archive.write(path, Path("DoPie") / path.relative_to(self.paths.project))

    def profile_requires_password(self, source: Path) -> bool:
        with zipfile.ZipFile(source) as archive:
            manifest = json.loads(archive.read("profile.json"))
        if manifest.get("format") != "dopie-portable-profile" or manifest.get("version") != 2:
            raise ValueError("Unsupported DoPie portable profile")
        return bool(manifest.get("requires_password", manifest.get("private_sources")))

    def import_portable_profile(self, source: Path, password: str | None = None) -> None:
        with tempfile.TemporaryDirectory(prefix="dopie-profile-", dir=self.paths.data) as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(source) as archive:
                root = staging.resolve()
                for member in archive.infolist():
                    destination = (staging / member.filename).resolve()
                    if not destination.is_relative_to(root):
                        raise ValueError(f"Unsafe profile member: {member.filename}")
                archive.extractall(staging)
            manifest = json.loads((staging / "profile.json").read_text(encoding="utf-8"))
            if manifest.get("format") != "dopie-portable-profile" or manifest.get("version") != 2:
                raise ValueError("Unsupported DoPie portable profile")
            imported_data = staging / "data"
            imported_vault = imported_data / "source-vault.dopie"
            imported_sources = imported_data / "sources.json"
            imported_preferences = imported_data / "preferences.json"
            if not imported_sources.exists():
                imported_sources.write_text("[]", encoding="utf-8")
            if not imported_preferences.exists():
                imported_preferences.write_text("{}", encoding="utf-8")
            SourceStore(imported_sources).load()
            portable_preferences = json.loads(imported_preferences.read_text(encoding="utf-8"))
            if not isinstance(portable_preferences, dict):
                raise ValueError("Portable preferences must be a JSON object")
            merged_preferences = SettingsStore(self.paths.settings).load()
            merged_preferences.update(portable_preferences)
            imported_preferences.write_text(json.dumps(merged_preferences, indent=2), encoding="utf-8")
            if manifest.get("private_sources"):
                requires_password = manifest.get("requires_password", True)
                if requires_password and not password:
                    raise ValueError("The transfer password is required")
                staged_vault = imported_data / "authorized-source-vault.dopie"
                staged_key = imported_data / "authorized-source-vault.key"
                VaultStore(staged_vault, staged_key).import_from_transfer(
                    imported_vault.read_bytes(), password if requires_password else ""
                )
                staged_vault.replace(self.paths.vault)
                staged_key.replace(self.paths.vault_key)
            else:
                self.paths.vault.unlink(missing_ok=True)
                self.paths.vault_key.unlink(missing_ok=True)
            for name, destination in (
                ("sources.json", self.paths.sources),
                ("preferences.json", self.paths.settings),
            ):
                imported = imported_data / name
                temporary = destination.with_suffix(".importing")
                shutil.copy2(imported, temporary)
                temporary.replace(destination)
