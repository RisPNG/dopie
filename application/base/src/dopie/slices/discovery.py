from __future__ import annotations

import json
from pathlib import Path

from dopie.models import SliceManifest


class SliceDiscovery:
    def __init__(self, bundled: Path, installed: Path):
        self.bundled = bundled
        self.installed = installed

    def discover_installed_slices(self) -> list[SliceManifest]:
        manifests: dict[str, SliceManifest] = {}
        if self.bundled.exists():
            for path in sorted(self.bundled.glob("*/slice.toml")):
                manifest = SliceManifest.load(path, origin="bundled")
                if manifest.id in manifests:
                    raise ValueError(f"Duplicate Slice id: {manifest.id}")
                manifests[manifest.id] = manifest
        if self.installed.exists():
            for path in sorted(self.installed.glob("*/slice.toml")):
                manifest = SliceManifest.load(path, origin="installed")
                if manifest.id in manifests:
                    raise ValueError(f"Duplicate Slice id: {manifest.id}")
                manifests[manifest.id] = manifest
            for state_path in sorted(self.installed.glob("*/current.json")):
                state = json.loads(state_path.read_text(encoding="utf-8"))
                path = state_path.parent / "versions" / str(state["version"]) / "slice.toml"
                manifest = SliceManifest.load(path, source_id=state.get("source_id"), origin="installed")
                if manifest.id in manifests:
                    raise ValueError(f"Duplicate Slice id: {manifest.id}")
                manifests[manifest.id] = manifest
        return sorted(manifests.values(), key=lambda item: item.name.casefold())
