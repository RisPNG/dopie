from __future__ import annotations

from dopie.context import ApplicationContext, VaultSession
from dopie.library.backend import LibraryBackend
from dopie.models import CatalogSlice, SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore


def test_library_includes_available_slices_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    bundled = tmp_path / "slices" / "local"
    bundled.mkdir(parents=True)
    bundled.joinpath("slice.toml").write_text(
        'id="local"\nname="Local"\nversion="1"\ndescription="Installed"\nentrypoint="frontend:Widget"',
        encoding="utf-8",
    )
    paths = resolve_app_paths()
    context = ApplicationContext(
        paths=paths,
        settings=SettingsStore(paths.settings),
        sources=SourceStore(paths.sources),
        vault=VaultSession(VaultStore(paths.vault, paths.vault_key)),
        discovery=SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        installer=SliceInstaller(paths.installed_slices),
        available=[
            CatalogSlice(
                "remote",
                "Remote",
                "1",
                "Available",
                "Other",
                "DoPie",
                "MIT",
                "https://example.test",
                "abc",
                "source",
            )
        ],
    )
    context.settings.save({"include_available_in_library": False})

    assert [item.id for item in LibraryBackend(context).build_library()] == ["local"]

    context.settings.save({"include_available_in_library": True})
    assert [item.id for item in LibraryBackend(context).build_library()] == ["local", "remote"]


def test_library_loads_available_slices_from_portable_cache(tmp_path, monkeypatch):
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
    context.settings.save({"include_available_in_library": True})
    context.sources.save([SourceDefinition("source", "Source", "https://github.com/owner/source")])
    paths.catalog_cache.joinpath("source.json").write_text(
        '[{"id":"remote","name":"Remote","version":"1","description":"Available",'
        '"download_url":"https://example.test/remote.zip","sha256":"abc"}]',
        encoding="utf-8",
    )

    SliceManagerBackend(context).load_cached_catalogs()

    assert [item.id for item in LibraryBackend(context).build_library()] == ["remote"]

    paths.catalog_cache.joinpath("source.json").write_text("not json", encoding="utf-8")

    assert SliceManagerBackend(context).load_cached_catalogs() == ()
