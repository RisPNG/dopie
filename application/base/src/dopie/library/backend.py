from __future__ import annotations

from dataclasses import dataclass

from dopie.context import ApplicationContext
from dopie.models import CatalogSlice, SliceManifest
from dopie.shared_folder import shared_folder_transaction


@dataclass(frozen=True)
class LibraryItem:
    id: str
    name: str
    version: str
    description: str
    category: str
    installed: bool
    favorite: bool = False
    manifest: SliceManifest | None = None
    catalog: CatalogSlice | None = None
    update: CatalogSlice | None = None
    source_id: str | None = None
    source_name: str = ""

    @property
    def key(self) -> str:
        return f"{self.source_id}/{self.id}" if self.source_id else self.id


class LibraryBackend:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def build_library(self, query: str = "", favorites_only: bool = False) -> list[LibraryItem]:
        installed = self.context.discovery.discover_installed_slices()
        with shared_folder_transaction(self.context.settings.path.parent / ".configuration.lock"):
            settings = self.context.settings.load()
            identities: dict[str, list[str]] = {}
            for manifest in installed:
                identities.setdefault(manifest.id, []).append(manifest.key)
            changed = False
            for setting in ("favorites", "recently_used"):
                previous = settings.get(setting, [])
                migrated = []
                for key in previous:
                    matches = identities.get(key, [])
                    replacement = matches[0] if len(matches) == 1 else key
                    if replacement not in migrated:
                        migrated.append(replacement)
                if migrated != previous:
                    settings[setting] = migrated
                    changed = True
            if changed:
                self.context.settings.save(settings)
        favorites = set(settings.get("favorites", []))
        recent = list(settings.get("recently_used", []))
        sources = {source.id: source.name for source in self.context.sources.load()}
        items = [
            LibraryItem(
                id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                category=manifest.category,
                installed=True,
                favorite=manifest.key in favorites,
                manifest=manifest,
                source_id=manifest.source_id,
                source_name=sources.get(manifest.source_id, manifest.source_id or ""),
                update=next(
                    (catalog for catalog in self.context.available if catalog.is_update_for(manifest)),
                    None,
                ),
            )
            for manifest in installed
        ]
        if settings.get("include_available_in_library"):
            installed_ids = {item.key for item in items}
            items.extend(
                LibraryItem(
                    id=item.id,
                    name=item.name,
                    version=item.version,
                    description=item.description,
                    category=item.category,
                    installed=False,
                    favorite=False,
                    catalog=item,
                    source_id=item.source_id,
                    source_name=sources.get(item.source_id, item.source_id),
                )
                for item in self.context.available
                if item.key not in installed_ids
            )
        normalized = query.strip().casefold()
        if normalized:
            items = [
                item
                for item in items
                if normalized in item.name.casefold()
                or normalized in item.description.casefold()
                or normalized in item.category.casefold()
            ]
        if favorites_only:
            items = [item for item in items if item.favorite]
        recent_order = {slice_id: index for index, slice_id in enumerate(recent)}
        return sorted(
            items,
            key=lambda item: (
                not item.installed,
                not item.favorite,
                recent_order.get(item.key, len(recent_order)),
                item.name.casefold(),
            ),
        )

    def set_slice_favorite(self, slice_id: str, favorite: bool) -> None:
        with shared_folder_transaction(self.context.settings.path.parent / ".configuration.lock"):
            settings = self.context.settings.load()
            favorites = set(settings.get("favorites", []))
            if favorite:
                favorites.add(slice_id)
            else:
                favorites.discard(slice_id)
            settings["favorites"] = sorted(favorites)
            self.context.settings.save(settings)

    def record_slice_opened(self, slice_id: str) -> None:
        with shared_folder_transaction(self.context.settings.path.parent / ".configuration.lock"):
            settings = self.context.settings.load()
            recent = [existing for existing in settings.get("recently_used", []) if existing != slice_id]
            recent.insert(0, slice_id)
            settings["recently_used"] = recent[:20]
            self.context.settings.save(settings)
