from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from packaging.version import InvalidVersion, Version

from dopie.context import ApplicationContext
from dopie.models import CatalogSlice, SliceManifest, SourceDefinition
from dopie.slices.compatibility import evaluate_slice_compatibility
from dopie.sources.catalog import SourceCatalog


@dataclass(frozen=True)
class CatalogRefresh:
    items: tuple[CatalogSlice, ...]
    errors: tuple[str, ...]


class SliceManagerBackend:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def installed_slices(self) -> list[SliceManifest]:
        return self.context.discovery.discover_installed_slices()

    def refresh_source_catalogs(self) -> CatalogRefresh:
        available: dict[str, CatalogSlice] = {}
        errors: list[str] = []
        for source in self.context.sources.load():
            if not source.enabled:
                continue
            cache = self.context.paths.catalog_cache / f"{source.id}.json"
            try:
                token = self.context.vault.source_credential(source.credential)
                items = SourceCatalog().fetch_available_slices(source, token)
                cache.write_text(json.dumps([asdict(item) for item in items], indent=2), encoding="utf-8")
            except Exception as error:
                errors.append(f"{source.name}: {error}")
                if not cache.exists():
                    continue
                items = [
                    CatalogSlice.from_dict(item, source.id) for item in json.loads(cache.read_text(encoding="utf-8"))
                ]
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

    def slice_update_available(self, item: CatalogSlice, installed: dict[str, SliceManifest]) -> bool:
        if item.id not in installed:
            return False
        try:
            return Version(item.version) > Version(installed[item.id].version)
        except InvalidVersion:
            return item.version != installed[item.id].version

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
                    provider=source.provider,
                    repository=source.repository,
                    reference=source.reference,
                    index=source.index,
                    base_url=source.base_url,
                    credential=source.credential,
                    public_key=source.public_key,
                    enabled=enabled if source.id == source_id else source.enabled,
                )
                for source in sources
            ]
        )

    def remove_source(self, source_id: str) -> None:
        sources = self.context.sources.load()
        source = next(source for source in sources if source.id == source_id)
        if source.credential:
            self.context.vault.remove_source_credential(source.credential)
        self.context.sources.save([source for source in sources if source.id != source_id])
