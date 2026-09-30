from __future__ import annotations

from dataclasses import dataclass, field

from dopie.models import CatalogSlice
from dopie.paths import AppPaths
from dopie.security.vault import VaultStore
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore


@dataclass
class ApplicationContext:
    paths: AppPaths
    settings: SettingsStore
    shared_settings: SettingsStore
    sources: SourceStore
    vault: VaultStore
    discovery: SliceDiscovery
    installer: SliceInstaller
    available: list[CatalogSlice] = field(default_factory=list)
