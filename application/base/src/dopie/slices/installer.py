from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from dopie.models import CatalogSlice, SliceManifest
from dopie.shared_folder import shared_folder_transaction


def migrate_legacy_slices(installed: Path) -> None:
    with shared_folder_transaction(installed / ".configuration.lock"):
        staging = installed / ".legacy-slices"
        migrations: list[tuple[Path, Path]] = []
        destinations: set[Path] = set()
        legacy_roots = [*sorted(installed.iterdir()), *(sorted(staging.iterdir()) if staging.exists() else [])]
        for root in legacy_roots:
            state_path = root / "current.json"
            if not state_path.exists() and not (root / "slice.toml").exists():
                continue
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
            namespace = (
                installed / "sources" / str(state["source_id"]) if state.get("source_id") else installed / "local"
            )
            destination = namespace / root.name
            if destination.exists() or destination in destinations:
                raise ValueError(f"Slice migration destination already exists: {destination}")
            if root.parent == installed and (staging / root.name).exists():
                raise ValueError(f"Slice migration is already staged: {root.name}")
            migrations.append((root, destination))
            destinations.add(destination)
        if not migrations:
            if staging.exists():
                staging.rmdir()
            return
        staging.mkdir(exist_ok=True)
        for root, _ in migrations:
            if root.parent == installed:
                root.rename(staging / root.name)
        for root, destination in migrations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            (staging / root.name).rename(destination)
        staging.rmdir()


class SliceInstaller:
    def __init__(self, installed: Path):
        self.installed = installed
        self.installed.mkdir(parents=True, exist_ok=True)
        migrate_legacy_slices(self.installed)

    def install_slice(self, item: CatalogSlice, archive: bytes) -> None:
        digest = hashlib.sha256(archive).hexdigest()
        if digest != item.sha256.removeprefix("sha256:"):
            raise ValueError(f"Checksum verification failed for {item.name}")
        with tempfile.TemporaryDirectory(prefix="dopie-slice-", dir=self.installed) as temporary:
            staging = Path(temporary) / item.id
            staging.mkdir()
            with zipfile.ZipFile(BytesIO(archive)) as package:
                root = staging.resolve()
                for member in package.infolist():
                    destination = (staging / member.filename).resolve()
                    if not destination.is_relative_to(root):
                        raise ValueError(f"Unsafe package member: {member.filename}")
                package.extractall(staging)
            candidates = list(staging.rglob("slice.toml"))
            if len(candidates) != 1:
                raise ValueError(f"{item.name} package must contain one slice.toml")
            package_root = candidates[0].parent
            manifest = SliceManifest.load(candidates[0], source_id=item.source_id, origin="installed")
            if manifest.id != item.id or manifest.version != item.version:
                raise ValueError(f"{item.name} package identity does not match its Source catalogue")
            if manifest.interface != "standard":
                raise ValueError("Downloaded Slices must use the standard interface")
            with shared_folder_transaction(self.installed / ".configuration.lock"):
                slice_root = self.installed / "sources" / item.source_id / item.id
                versions = slice_root / "versions"
                versions.mkdir(parents=True, exist_ok=True)
                destination = versions / item.version
                prepared = versions / f".{item.version}.prepared"
                if prepared.exists():
                    shutil.rmtree(prepared)
                shutil.copytree(package_root, prepared)
                if destination.exists():
                    shutil.rmtree(destination)
                prepared.replace(destination)
                state = {"version": item.version, "source_id": item.source_id}
                temporary_state = slice_root / "current.tmp"
                temporary_state.write_text(json.dumps(state, indent=2), encoding="utf-8")
                temporary_state.replace(slice_root / "current.json")

    def activate_slice_version(self, slice_id: str, version: str, source_id: str | None = None) -> None:
        with shared_folder_transaction(self.installed / ".configuration.lock"):
            root = (self.installed / "sources" / source_id if source_id else self.installed / "local") / slice_id
            destination = root / "versions" / version / "slice.toml"
            if not destination.exists():
                raise ValueError(f"Slice version is not installed: {slice_id} {version}")
            state_path = root / "current.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["version"] = version
            temporary = root / "current.tmp"
            temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temporary.replace(state_path)

    def installed_versions(self, slice_id: str, source_id: str | None = None) -> list[str]:
        with shared_folder_transaction(self.installed / ".configuration.lock"):
            namespace = self.installed / "sources" / source_id if source_id else self.installed / "local"
            versions = namespace / slice_id / "versions"
            if not versions.exists():
                return []
            return sorted(path.name for path in versions.iterdir() if path.is_dir() and not path.name.startswith("."))

    def uninstall_slice(self, slice_id: str, source_id: str | None = None) -> None:
        with shared_folder_transaction(self.installed / ".configuration.lock"):
            destination = (self.installed / "sources" / source_id if source_id else self.installed / "local") / slice_id
            if destination.exists():
                shutil.rmtree(destination)
