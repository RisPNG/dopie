from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dopie.models import CatalogSlice
from dopie.paths import AppPaths
from dopie.security.vault import VaultStore
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore


class VaultSession:
    def __init__(self, store: VaultStore):
        self.store = store
        self.secrets: dict[str, Any] | None = None
        self.password: str | None = None

    def unlock_private_sources(self, password: str) -> None:
        self.secrets = self.store.unlock(password)
        self.password = password

    def create_private_source_vault(self, password: str) -> None:
        self.secrets = {"credentials": {}}
        self.password = password
        self.store.seal(self.secrets, password)

    def store_source_credential(self, credential_id: str, token: str) -> None:
        if self.secrets is None or self.password is None:
            raise RuntimeError("Private Sources are locked")
        self.secrets.setdefault("credentials", {})[credential_id] = token
        self.store.seal(self.secrets, self.password)

    def source_credential(self, credential_id: str | None) -> str | None:
        if credential_id is None:
            return None
        if self.secrets is None:
            raise RuntimeError("Private Sources are locked")
        return str(self.secrets["credentials"][credential_id])

    def remove_source_credential(self, credential_id: str) -> None:
        if self.secrets is None or self.password is None:
            raise RuntimeError("Private Sources are locked")
        self.secrets.get("credentials", {}).pop(credential_id, None)
        self.store.seal(self.secrets, self.password)

    def lock_private_sources(self) -> None:
        self.secrets = None
        self.password = None


@dataclass
class ApplicationContext:
    paths: AppPaths
    settings: SettingsStore
    sources: SourceStore
    vault: VaultSession
    discovery: SliceDiscovery
    installer: SliceInstaller
    available: list[CatalogSlice] = field(default_factory=list)
