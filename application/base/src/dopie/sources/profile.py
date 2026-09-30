from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from dopie.paths import AppPaths
from dopie.security.vault import VaultStore
from dopie.shared_folder import shared_folder_transaction
from dopie.storage import DEFAULT_SHARED_SETTINGS, SettingsStore, SourceStore


class PortableProfileService:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def export_portable_profile(
        self,
        destination: Path,
        password: str | None = None,
    ) -> None:
        with (
            shared_folder_transaction(self.paths.data / ".configuration.lock"),
            shared_folder_transaction(self.paths.settings.parent / ".configuration.lock"),
        ):
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
                    key: settings[key] for key in ("theme", "include_available_in_library", "check_updates_on_launch")
                }
                portable_settings["application_update_source"] = SettingsStore(
                    self.paths.shared_settings, DEFAULT_SHARED_SETTINGS
                ).load()["application_update_source"]
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
        with (
            shared_folder_transaction(self.paths.data / ".configuration.lock"),
            shared_folder_transaction(self.paths.settings.parent / ".configuration.lock"),
        ):
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
                imported_source_list = SourceStore(imported_sources).load()
                portable_preferences = json.loads(imported_preferences.read_text(encoding="utf-8"))
                if not isinstance(portable_preferences, dict):
                    raise ValueError("Portable preferences must be a JSON object")
                shared_preferences = SettingsStore(self.paths.shared_settings, DEFAULT_SHARED_SETTINGS).load()
                preferences = SettingsStore(self.paths.settings).load()
                shared_preferences["application_update_source"] = portable_preferences.pop(
                    "application_update_source", shared_preferences["application_update_source"]
                )
                preferences.update(portable_preferences)
                SourceStore(imported_sources).save(imported_source_list)
                SettingsStore(imported_preferences).save(preferences)
                imported_shared_preferences = imported_data / "shared-preferences.json"
                SettingsStore(imported_shared_preferences, DEFAULT_SHARED_SETTINGS).save(shared_preferences)
                publications: list[tuple[Path | None, Path]] = []
                if manifest.get("private_sources"):
                    requires_password = manifest.get("requires_password", True)
                    if requires_password and not password:
                        raise ValueError("The transfer password is required")
                    staged_vault = imported_data / "authorized-source-vault.dopie"
                    staged_key = imported_data / "authorized-source-vault.key"
                    staged = VaultStore(staged_vault, staged_key)
                    staged.import_from_transfer(imported_vault.read_bytes(), password if requires_password else "")
                    secrets = staged.unlock()
                    if self.paths.vault_key.exists():
                        shutil.copy2(self.paths.vault_key, staged_key)
                        staged.seal(secrets)
                    else:
                        publications.append((staged_key, self.paths.vault_key))
                    publications.append((staged_vault, self.paths.vault))
                else:
                    publications.extend(((None, self.paths.vault), (None, self.paths.vault_key)))
                publications.extend(
                    (
                        (imported_sources, self.paths.sources),
                        (imported_shared_preferences, self.paths.shared_settings),
                        (imported_preferences, self.paths.settings),
                    )
                )
                backups = staging / "rollback"
                backups.mkdir()
                originals: dict[Path, Path | None] = {}
                for index, (_, destination) in enumerate(publications):
                    if destination.exists():
                        backup = backups / str(index)
                        shutil.copy2(destination, backup)
                        originals[destination] = backup
                    else:
                        originals[destination] = None
                published: list[Path] = []
                try:
                    for imported, destination in publications:
                        if imported is None:
                            destination.unlink(missing_ok=True)
                        else:
                            imported.replace(destination)
                        published.append(destination)
                except OSError:
                    for destination in reversed(published):
                        backup = originals[destination]
                        if backup is None:
                            destination.unlink(missing_ok=True)
                        else:
                            backup.replace(destination)
                    raise
