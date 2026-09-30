from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any

from dopie.models import SourceDefinition

DEFAULT_SETTINGS = {
    "theme": "system",
    "include_available_in_library": False,
    "check_updates_on_launch": True,
    "last_seen_version": None,
    "favorites": [],
    "recently_used": [],
}

DEFAULT_SHARED_SETTINGS = {
    "application_update_source": {
        "id": "dopie-application",
        "name": "DoPie Application",
        "repository_url": "https://github.com/RisPNG/dopie",
        "reference": "main",
        "index": "index.json",
        "credential": None,
    },
}


class SettingsStore:
    def __init__(self, path: Path, defaults: dict[str, Any] = DEFAULT_SETTINGS):
        self.path = path
        self.defaults = defaults

    def load(self) -> dict[str, Any]:
        stored = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        settings = copy.deepcopy(self.defaults)
        settings.update(stored)
        return settings

    def save(self, settings: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
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
                "repository_url": source.repository_url,
                "reference": source.reference,
                "index": source.index,
                "credential": source.credential,
                "enabled": source.enabled,
            }
            for source in sources
        ]
        temporary = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)
