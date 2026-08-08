from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from dopie.paths import AppPaths


class PortableProfileService:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def export_portable_profile(self, destination: Path, include_slices: bool = True) -> None:
        manifest = {"format": "dopie-portable-profile", "version": 1, "includes_slices": include_slices}
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("profile.json", json.dumps(manifest, indent=2))
            if self.paths.sources.exists():
                archive.write(self.paths.sources, "data/sources.json")
            if self.paths.vault.exists():
                archive.write(self.paths.vault, "data/source-vault.dopie")
            if self.paths.settings.exists():
                settings = json.loads(self.paths.settings.read_text(encoding="utf-8"))
                portable_settings = {
                    key: settings[key]
                    for key in (
                        "theme",
                        "vault_lock_minutes",
                        "include_available_in_library",
                        "check_updates_on_launch",
                        "application_update_source",
                    )
                    if key in settings
                }
                archive.writestr("data/preferences.json", json.dumps(portable_settings, indent=2))
            if include_slices:
                for path in self.paths.installed_slices.rglob("*"):
                    if path.is_file():
                        archive.write(path, Path("data/slices") / path.relative_to(self.paths.installed_slices))

    def import_portable_profile(self, source: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="dopie-profile-") as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(source) as archive:
                root = staging.resolve()
                for member in archive.infolist():
                    destination = (staging / member.filename).resolve()
                    if not destination.is_relative_to(root):
                        raise ValueError(f"Unsafe profile member: {member.filename}")
                archive.extractall(staging)
            manifest = json.loads((staging / "profile.json").read_text(encoding="utf-8"))
            if manifest.get("format") != "dopie-portable-profile" or manifest.get("version") != 1:
                raise ValueError("Unsupported DoPie portable profile")
            imported_data = staging / "data"
            for name, destination in (
                ("sources.json", self.paths.sources),
                ("source-vault.dopie", self.paths.vault),
                ("preferences.json", self.paths.settings),
            ):
                imported = imported_data / name
                if imported.exists():
                    shutil.copy2(imported, destination)
            imported_slices = imported_data / "slices"
            if imported_slices.exists():
                for slice_root in imported_slices.iterdir():
                    destination = self.paths.installed_slices / slice_root.name
                    if destination.exists():
                        shutil.rmtree(destination)
                    shutil.copytree(slice_root, destination)
