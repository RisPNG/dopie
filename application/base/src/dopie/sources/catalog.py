from __future__ import annotations

import json

from dopie.models import CatalogSlice, SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient


class SourceCatalog:
    def fetch_available_slices(
        self,
        source: SourceDefinition,
        token: str | None = None,
        revision: str | None = None,
    ) -> list[CatalogSlice]:
        revision = revision or RemoteRepositoryClient(source, token).resolve_revision()
        payload = RemoteRepositoryClient(source, token).read_repository_file(source.index, revision)
        data = json.loads(payload)
        items = data["slices"] if isinstance(data, dict) else data
        return sorted(
            [CatalogSlice.from_dict(item, source.id) for item in items],
            key=lambda item: item.name.casefold(),
        )
