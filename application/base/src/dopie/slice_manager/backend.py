from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from dopie.context import ApplicationContext
from dopie.models import CatalogSlice, SliceManifest, SourceDefinition
from dopie.slices.compatibility import evaluate_slice_compatibility
from dopie.sources.catalog import SourceCatalog
from dopie.sources.remote import RemoteRepositoryClient


@dataclass(frozen=True)
class CatalogRefresh:
    items: tuple[CatalogSlice, ...]
    errors: tuple[str, ...]


class SliceManagerBackend:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def installed_slices(self) -> list[SliceManifest]:
        return self.context.discovery.discover_installed_slices()

    def load_source_catalog(self, source: SourceDefinition) -> tuple[str | None, list[CatalogSlice]]:
        cache = self.context.paths.catalog_cache / f"{source.id}.json"
        data = json.loads(cache.read_text(encoding="utf-8"))
        revision = str(data["revision"]) if isinstance(data, dict) and data.get("revision") else None
        cached_items = data["items"] if isinstance(data, dict) else data
        return revision, [CatalogSlice.from_dict(item, source.id) for item in cached_items]

    def load_cached_catalogs(self) -> tuple[CatalogSlice, ...]:
        available: dict[str, CatalogSlice] = {}
        for source in self.context.sources.load():
            cache = self.context.paths.catalog_cache / f"{source.id}.json"
            if not source.enabled or not cache.exists():
                continue
            try:
                _, cached_items = self.load_source_catalog(source)
                for catalog_slice in cached_items:
                    available[catalog_slice.id] = catalog_slice
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        self.context.available = sorted(available.values(), key=lambda item: item.name.casefold())
        return tuple(self.context.available)

    def source_catalogs_are_stale(self, max_age_seconds: int) -> bool:
        checked_at = time.time()
        enabled_sources = [source for source in self.context.sources.load() if source.enabled]
        return any(
            not (cache := self.context.paths.catalog_cache / f"{source.id}.json").exists()
            or checked_at - cache.stat().st_mtime >= max_age_seconds
            for source in enabled_sources
        )

    def refresh_source_catalogs(self, source_ids: set[str] | None = None) -> CatalogRefresh:
        available: dict[str, CatalogSlice] = {}
        errors: list[str] = []
        for source in self.context.sources.load():
            if not source.enabled:
                continue
            cache = self.context.paths.catalog_cache / f"{source.id}.json"
            cached_revision = None
            cached_items: list[CatalogSlice] = []
            if cache.exists():
                try:
                    cached_revision, cached_items = self.load_source_catalog(source)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    pass
            if source_ids is not None and source.id not in source_ids:
                for item in cached_items:
                    available[item.id] = item
                continue
            try:
                token = self.context.vault.source_credential(source.credential)
                revision = RemoteRepositoryClient(source, token).resolve_revision()
                items = (
                    cached_items
                    if cached_revision == revision
                    else SourceCatalog().fetch_available_slices(source, token, revision)
                )
                temporary = cache.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"revision": revision, "items": [asdict(item) for item in items]}, indent=2),
                    encoding="utf-8",
                )
                temporary.replace(cache)
            except Exception as error:
                errors.append(f"{source.name}: {error}")
                if not cached_items:
                    continue
                items = cached_items
            for item in items:
                available[item.id] = item
        self.context.available = sorted(available.values(), key=lambda item: item.name.casefold())
        return CatalogRefresh(tuple(self.context.available), tuple(errors))

    def install_catalog_slice(self, item: CatalogSlice) -> None:
        compatibility = evaluate_slice_compatibility(item)
        if not compatibility.compatible:
            raise ValueError(compatibility.reason)
        source = next(source for source in self.context.sources.load() if source.id == item.source_id)
        token = self.context.vault.source_credential(source.credential)
        self.context.installer.install_slice(item, source, token)

    def uninstall_managed_slice(self, manifest: SliceManifest) -> None:
        if manifest.origin != "installed":
            raise ValueError("Bundled Slices cannot be uninstalled")
        self.context.installer.uninstall_slice(manifest.id)

    def rollback_slice(self, manifest: SliceManifest, version: str) -> None:
        if manifest.origin != "installed":
            raise ValueError("Bundled Slices do not have managed rollback versions")
        self.context.installer.activate_slice_version(manifest.id, version)

    def add_source(self, source: SourceDefinition, token: str | None = None) -> None:
        sources = self.context.sources.load()
        if any(existing.id == source.id for existing in sources):
            raise ValueError(f"Source id already exists: {source.id}")
        if token and source.credential:
            self.context.vault.store_source_credential(source.credential, token)
        sources.append(source)
        self.context.sources.save(sources)

    def set_source_enabled(self, source_id: str, enabled: bool) -> None:
        sources = self.context.sources.load()
        self.context.sources.save(
            [
                SourceDefinition(
                    id=source.id,
                    name=source.name,
                    repository_url=source.repository_url,
                    reference=source.reference,
                    index=source.index,
                    credential=source.credential,
                    enabled=enabled if source.id == source_id else source.enabled,
                )
                for source in sources
            ]
        )

    def update_source(self, original_id: str, updated: SourceDefinition, token: str | None = None) -> None:
        sources = self.context.sources.load()
        original = next(source for source in sources if source.id == original_id)
        if any(source.id == updated.id and source.id != original_id for source in sources):
            raise ValueError(f"Source id already exists: {updated.id}")
        if token and updated.credential:
            self.context.vault.store_source_credential(updated.credential, token)
        if original.credential and original.credential != updated.credential:
            self.context.vault.remove_source_credential(original.credential)
        self.context.sources.save([updated if source.id == original_id else source for source in sources])
        if original_id != updated.id:
            original_cache = self.context.paths.catalog_cache / f"{original_id}.json"
            updated_cache = self.context.paths.catalog_cache / f"{updated.id}.json"
            if original_cache.exists():
                original_cache.replace(updated_cache)
        self.load_cached_catalogs()

    def remove_source(self, source_id: str) -> None:
        sources = self.context.sources.load()
        source = next(source for source in sources if source.id == source_id)
        if source.credential:
            self.context.vault.remove_source_credential(source.credential)
        self.context.sources.save([source for source in sources if source.id != source_id])
        cache = self.context.paths.catalog_cache / f"{source_id}.json"
        if cache.exists():
            cache.unlink()
        self.load_cached_catalogs()
