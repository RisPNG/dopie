from __future__ import annotations

from dopie.context import ApplicationContext, VaultSession
from dopie.models import SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore


def test_source_can_be_edited_and_made_public_without_losing_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    paths = resolve_app_paths()
    context = ApplicationContext(
        paths=paths,
        settings=SettingsStore(paths.settings),
        sources=SourceStore(paths.sources),
        vault=VaultSession(VaultStore(paths.vault, paths.vault_key)),
        discovery=SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        installer=SliceInstaller(paths.installed_slices),
    )
    backend = SliceManagerBackend(context)
    original = SourceDefinition(
        "private",
        "Private",
        "https://github.com/owner/private",
        credential="source:private",
    )
    backend.add_source(original, "private-token")
    paths.catalog_cache.joinpath("private.json").write_text("[]", encoding="utf-8")
    updated = SourceDefinition("renamed", "Renamed", "https://code.example.test/owner/public")

    backend.update_source("private", updated)

    assert context.sources.load() == [updated]
    assert not paths.catalog_cache.joinpath("private.json").exists()
    assert paths.catalog_cache.joinpath("renamed.json").exists()
    assert context.vault.secrets == {"credentials": {}}
