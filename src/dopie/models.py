from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SliceManifest:
    id: str
    name: str
    version: str
    description: str
    interface: str
    entrypoint: str | None
    operation: str | None
    inputs: tuple[dict[str, Any], ...]
    assets: tuple[dict[str, str], ...]
    category: str
    author: str
    license: str
    path: Path
    api_version: int = 1
    python: str = ">=3.11"
    platforms: tuple[str, ...] = ()
    architectures: tuple[str, ...] = ()
    origin: str = "bundled"
    source_id: str | None = None

    @classmethod
    def load(cls, path: Path, source_id: str | None = None, origin: str = "bundled") -> SliceManifest:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        required = ("id", "name", "version", "description")
        missing = [field for field in required if not data.get(field)]
        if missing:
            raise ValueError(f"{path} is missing: {', '.join(missing)}")
        interface = str(data.get("interface", "custom"))
        entrypoint = str(data["entrypoint"]) if data.get("entrypoint") else None
        operation = str(data["operation"]) if data.get("operation") else None
        if interface == "custom" and not entrypoint:
            raise ValueError(f"{path} requires an entrypoint for its custom interface")
        if interface == "standard" and not operation:
            raise ValueError(f"{path} requires an operation for its standard interface")
        if interface not in {"custom", "standard"}:
            raise ValueError(f"{path} has an unsupported interface: {interface}")
        inputs = tuple(data.get("inputs", []))
        if any(str(item.get("id")) == "_assets" for item in inputs):
            raise ValueError(f"{path} uses the reserved input id: _assets")
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data["description"]),
            interface=interface,
            entrypoint=entrypoint,
            operation=operation,
            inputs=inputs,
            assets=tuple(
                {
                    "id": str(asset["id"]),
                    "url": str(asset["url"]),
                    "sha256": str(asset["sha256"]),
                }
                for asset in data.get("assets", [])
            ),
            category=str(data.get("category", "Other")),
            author=str(data.get("author", "Unknown")),
            license=str(data.get("license", "Unknown")),
            path=path.parent,
            api_version=int(data.get("api-version", 1)),
            python=str(data.get("python", ">=3.11")),
            platforms=tuple(str(item) for item in data.get("platforms", [])),
            architectures=tuple(str(item) for item in data.get("architectures", [])),
            origin=origin,
            source_id=source_id,
        )


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    name: str
    provider: str
    repository: str
    reference: str = "main"
    index: str = "index.json"
    base_url: str | None = None
    credential: str | None = None
    public_key: str | None = None
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceDefinition:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            provider=str(data["provider"]),
            repository=str(data["repository"]),
            reference=str(data.get("reference", "main")),
            index=str(data.get("index", "index.json")),
            base_url=str(data["base_url"]) if data.get("base_url") else None,
            credential=str(data["credential"]) if data.get("credential") else None,
            public_key=str(data["public_key"]) if data.get("public_key") else None,
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True)
class CatalogSlice:
    id: str
    name: str
    version: str
    description: str
    category: str
    author: str
    license: str
    download_url: str
    sha256: str
    source_id: str
    api_version: int = 1
    python: str = ">=3.11"
    platforms: tuple[str, ...] = ()
    architectures: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_id: str) -> CatalogSlice:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data["description"]),
            category=str(data.get("category", "Other")),
            author=str(data.get("author", "Unknown")),
            license=str(data.get("license", "Unknown")),
            download_url=str(data["download_url"]),
            sha256=str(data["sha256"]),
            source_id=source_id,
            api_version=int(data.get("api_version", 1)),
            python=str(data.get("python", ">=3.11")),
            platforms=tuple(str(item) for item in data.get("platforms", [])),
            architectures=tuple(str(item) for item in data.get("architectures", [])),
        )
