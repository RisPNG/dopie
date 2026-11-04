from __future__ import annotations

import json
from pathlib import Path

from dopie.models import SliceManifest
from dopie.shared_folder import shared_folder_transaction
from dopie.slices.installer import migrate_legacy_slices


class SliceDiscovery:
    def __init__(self, bundled: Path, installed: Path):
        self.bundled = bundled
        self.installed = installed

    def discover_installed_slices(self) -> list[SliceManifest]:
        manifests: dict[str, SliceManifest] = {}
        if self.bundled.exists():
            for path in sorted(self.bundled.glob("*/slice.toml")):
                manifest = SliceManifest.load(path, origin="bundled")
                if manifest.key in manifests:
                    raise ValueError(f"Duplicate Slice id: {manifest.key}")
                manifests[manifest.key] = manifest
        if self.installed.exists():
            with shared_folder_transaction(self.installed / ".configuration.lock"):
                migrate_legacy_slices(self.installed)
                for path in sorted(self.installed.glob("local/*/slice.toml")):
                    manifest = SliceManifest.load(path, origin="installed")
                    if manifest.key in manifests:
                        raise ValueError(f"Duplicate Slice id: {manifest.key}")
                    manifests[manifest.key] = manifest
                states = [
                    *self.installed.glob("local/*/current.json"), *self.installed.glob("sources/*/*/current.json")
                ]
                for state_path in sorted(states):
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                    path = state_path.parent / "versions" / str(state["version"]) / "slice.toml"
                    manifest = SliceManifest.load(path, source_id=state.get("source_id"), origin="installed")
                    if manifest.key in manifests:
                        raise ValueError(f"Duplicate Slice id: {manifest.key}")
                    manifests[manifest.key] = manifest
        return sorted(manifests.values(), key=lambda item: item.name.casefold())
