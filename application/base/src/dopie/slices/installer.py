from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from dopie.models import CatalogSlice, SliceManifest, SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient


class SliceInstaller:
    def __init__(self, installed: Path):
        self.installed = installed
        self.installed.mkdir(parents=True, exist_ok=True)

    def install_slice(
        self,
        item: CatalogSlice,
        source: SourceDefinition,
        token: str | None = None,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        client = RemoteRepositoryClient(source, token)
        archive = (
            client.download_artifact(item.download_url)
            if progress is None
            else client.download_artifact(item.download_url, progress)
        )
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
            slice_root = self.installed / item.id
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

    def activate_slice_version(self, slice_id: str, version: str) -> None:
        root = self.installed / slice_id
        destination = root / "versions" / version / "slice.toml"
        if not destination.exists():
            raise ValueError(f"Slice version is not installed: {slice_id} {version}")
        state_path = root / "current.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["version"] = version
        temporary = root / "current.tmp"
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(state_path)

    def installed_versions(self, slice_id: str) -> list[str]:
        versions = self.installed / slice_id / "versions"
        if not versions.exists():
            return []
        return sorted(path.name for path in versions.iterdir() if path.is_dir() and not path.name.startswith("."))

    def uninstall_slice(self, slice_id: str) -> None:
        destination = self.installed / slice_id
        if destination.exists():
            shutil.rmtree(destination)
