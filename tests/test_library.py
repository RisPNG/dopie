from __future__ import annotations

from dopie.context import ApplicationContext, VaultSession
from dopie.library.backend import LibraryBackend
from dopie.models import CatalogSlice
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore


def test_library_includes_available_slices_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    (tmp_path / "portable.toml").write_text('mode = "portable"', encoding="utf-8")
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
        vault=VaultSession(VaultStore(paths.vault)),
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
