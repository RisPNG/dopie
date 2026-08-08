from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopie.models import SourceDefinition


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "include_available_in_library": False,
                "check_updates_on_launch": True,
                "last_seen_version": None,
                "favorites": [],
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        temporary.replace(self.path)


class SourceStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[SourceDefinition]:
        if not self.path.exists():
            return []
        return [SourceDefinition.from_dict(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]

    def save(self, sources: list[SourceDefinition]) -> None:
        payload = [
            {
                "id": source.id,
                "name": source.name,
                "provider": source.provider,
                "repository": source.repository,
                "reference": source.reference,
                "index": source.index,
                "base_url": source.base_url,
                "credential": source.credential,
                "public_key": source.public_key,
                "enabled": source.enabled,
            }
            for source in sources
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)
