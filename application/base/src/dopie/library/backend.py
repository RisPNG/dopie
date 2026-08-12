from __future__ import annotations

from dataclasses import dataclass

from dopie.context import ApplicationContext
from dopie.models import CatalogSlice, SliceManifest


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


class LibraryBackend:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def build_library(self, query: str = "", favorites_only: bool = False) -> list[LibraryItem]:
        settings = self.context.settings.load()
        favorites = set(settings.get("favorites", []))
        recent = list(settings.get("recently_used", []))
        installed = self.context.discovery.discover_installed_slices()
        items = [
            LibraryItem(
                id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                category=manifest.category,
                installed=True,
                favorite=manifest.id in favorites,
                manifest=manifest,
                update=next(
                    (catalog for catalog in self.context.available if catalog.is_update_for(manifest)),
                    None,
                ),
            )
            for manifest in installed
        ]
        if settings.get("include_available_in_library"):
            installed_ids = {item.id for item in items}
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
                )
                for item in self.context.available
                if item.id not in installed_ids
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
                recent_order.get(item.id, len(recent_order)),
                item.name.casefold(),
            ),
        )

    def set_slice_favorite(self, slice_id: str, favorite: bool) -> None:
        settings = self.context.settings.load()
        favorites = set(settings.get("favorites", []))
        if favorite:
            favorites.add(slice_id)
        else:
            favorites.discard(slice_id)
        settings["favorites"] = sorted(favorites)
        self.context.settings.save(settings)

    def record_slice_opened(self, slice_id: str) -> None:
        settings = self.context.settings.load()
        recent = [existing for existing in settings.get("recently_used", []) if existing != slice_id]
        recent.insert(0, slice_id)
        settings["recently_used"] = recent[:20]
        self.context.settings.save(settings)
