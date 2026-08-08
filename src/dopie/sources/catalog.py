from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from dopie.models import CatalogSlice, SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient


class SourceCatalog:
    def fetch_available_slices(self, source: SourceDefinition, token: str | None = None) -> list[CatalogSlice]:
        revision = RemoteRepositoryClient(source, token).resolve_revision()
        payload = RemoteRepositoryClient(source, token).read_repository_file(source.index, revision)
        if source.public_key:
            signature = RemoteRepositoryClient(source, token).read_repository_file(f"{source.index}.sig", revision)
            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(source.public_key))
            public_key.verify(base64.b64decode(signature.strip()), payload)
        data = json.loads(payload)
        items = data["slices"] if isinstance(data, dict) else data
        return sorted(
            [CatalogSlice.from_dict(item, source.id) for item in items],
            key=lambda item: item.name.casefold(),
        )
