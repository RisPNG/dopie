from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict, replace
from io import BytesIO
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from dopie.context import ApplicationContext
from dopie.library.backend import LibraryBackend
from dopie.models import CatalogSlice, SliceManifest, SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.sources.remote import RemoteRepositoryClient
from dopie.storage import DEFAULT_SHARED_SETTINGS, SettingsStore, SourceStore
from dopie.workspace.frontend import StandardSliceWidget


def open_context(root, monkeypatch, user="alice"):
    monkeypatch.setenv("DOPIE_ROOT", str(root))
    monkeypatch.setenv("LOGNAME", user)
    paths = resolve_app_paths()
    return ApplicationContext(
        paths,
        SettingsStore(paths.settings),
        SettingsStore(paths.shared_settings, DEFAULT_SHARED_SETTINGS),
        SourceStore(paths.sources),
        VaultStore(paths.vault, paths.vault_key),
        SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        SliceInstaller(paths.installed_slices),
    )


def catalog_item(source_id, version="1.0.0"):
    return CatalogSlice(
        "tool",
        f"{source_id.title()} Tool",
        version,
        "Process a workbook",
        "Spreadsheets",
        source_id,
        "MIT",
        f"https://example.test/{source_id}/tool-{version}.zip",
        "0" * 64,
        source_id,
    )


def install_version(root, source_id, version="1.0.0"):
    path = root / "versions" / version
    path.mkdir(parents=True)
    path.joinpath("slice.toml").write_text(
        f'id="tool"\nname="{source_id.title()} Tool"\nversion="{version}"\ndescription="Process a workbook"\n'
        'interface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    path.joinpath("backend.py").write_text("def run(inputs, progress, log): return inputs\n", encoding="utf-8")
    root.joinpath("current.json").write_text(
        json.dumps({"version": version, "source_id": source_id}), encoding="utf-8"
    )
    return path / "slice.toml"


def test_cached_and_refreshed_catalogs_keep_each_sources_same_id(tmp_path, monkeypatch):
    context = open_context(tmp_path, monkeypatch)
    sources = [
        SourceDefinition(source_id, source_id.title(), f"https://github.com/owner/{source_id}")
        for source_id in ("alpha", "beta")
    ]
    context.sources.save(sources)
    for source in sources:
        context.paths.catalog_cache.joinpath(f"{source.id}.json").write_text(
            json.dumps({"revision": "previous", "items": [asdict(catalog_item(source.id))]}), encoding="utf-8"
        )
    backend = SliceManagerBackend(context)

    assert {item.key for item in backend.load_cached_catalogs()} == {"alpha/tool", "beta/tool"}

    requests = []
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: f"{self.source.id}-current")

    def read_catalog(client, path, revision):
        requests.append((client.source.id, revision))
        return json.dumps({"slices": [asdict(catalog_item(client.source.id, "2.0.0"))]}).encode("utf-8")

    monkeypatch.setattr(RemoteRepositoryClient, "read_repository_file", read_catalog)

    refreshed = backend.refresh_source_catalogs({"alpha"})

    assert refreshed.errors == ()
    assert {item.key: item.version for item in refreshed.items} == {"alpha/tool": "2.0.0", "beta/tool": "1.0.0"}
    assert requests == [("alpha", "alpha-current")]

    refreshed = backend.refresh_source_catalogs()

    assert refreshed.errors == ()
    assert {item.key: item.version for item in refreshed.items} == {"alpha/tool": "2.0.0", "beta/tool": "2.0.0"}
    assert {item.key: item.version for item in backend.load_cached_catalogs()} == {
        "alpha/tool": "2.0.0",
        "beta/tool": "2.0.0",
    }


def test_library_distinguishes_bundled_installed_and_available_same_id(tmp_path, monkeypatch):
    context = open_context(tmp_path, monkeypatch)
    bundled = context.paths.bundled_slices / "tool"
    bundled.mkdir(parents=True)
    bundled.joinpath("slice.toml").write_text(
        'id="tool"\nname="Bundled Tool"\nversion="1.0.0"\ndescription="Bundled"\n'
        'interface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    install_version(context.paths.installed_slices / "sources" / "alpha" / "tool", "alpha")
    context.available = [catalog_item("alpha", "2.0.0"), catalog_item("beta", "3.0.0")]
    context.settings.save({"include_available_in_library": True})

    items = {item.key: item for item in LibraryBackend(context).build_library()}

    assert set(items) == {"tool", "alpha/tool", "beta/tool"}
    assert items["tool"].installed
    assert items["tool"].update is None
    assert items["alpha/tool"].installed
    assert items["alpha/tool"].update.version == "2.0.0"
    assert items["alpha/tool"].update.source_id == "alpha"
    assert not items["beta/tool"].installed
    assert items["beta/tool"].catalog.version == "3.0.0"


def test_legacy_favorites_and_recents_migrate_and_remain_independent(tmp_path, monkeypatch):
    context = open_context(tmp_path, monkeypatch)
    install_version(context.paths.installed_slices / "tool", "alpha")
    context.settings.save({"favorites": ["tool"], "recently_used": ["tool"]})
    backend = LibraryBackend(context)

    items = backend.build_library()

    assert [item.key for item in items] == ["alpha/tool"]
    assert items[0].favorite
    assert context.settings.load()["favorites"] == ["alpha/tool"]
    assert context.settings.load()["recently_used"] == ["alpha/tool"]
    install_version(context.paths.installed_slices / "sources" / "beta" / "tool", "beta")

    items = {item.key: item for item in backend.build_library()}

    assert items["alpha/tool"].favorite
    assert not items["beta/tool"].favorite
    backend.set_slice_favorite("beta/tool", True)
    backend.set_slice_favorite("alpha/tool", False)
    backend.record_slice_opened("beta/tool")
    backend.record_slice_opened("alpha/tool")

    assert [item.key for item in backend.build_library(favorites_only=True)] == ["beta/tool"]
    assert context.settings.load()["favorites"] == ["beta/tool"]
    assert context.settings.load()["recently_used"] == ["alpha/tool", "beta/tool"]


def test_same_id_source_assets_have_independent_workspace_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    widgets = []
    worker = Path(__file__).parents[1] / "application" / "base" / "src" / "dopie" / "slices" / "worker.py"
    try:
        for source_id in ("alpha", "beta"):
            manifest_path = install_version(tmp_path / "slices" / source_id / "tool", source_id)
            manifest = SliceManifest.load(manifest_path, source_id=source_id, origin="installed")
            widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", worker)
            widgets.append(widget)
            widget.asset_root.mkdir(parents=True)
            widget.asset_root.joinpath("model.bin").write_text(source_id, encoding="utf-8")

        assert widgets[0].asset_root != widgets[1].asset_root
        assert widgets[0].asset_root.joinpath("model.bin").read_text(encoding="utf-8") == "alpha"
        assert widgets[1].asset_root.joinpath("model.bin").read_text(encoding="utf-8") == "beta"
    finally:
        for widget in widgets:
            widget.close()
            widget.deleteLater()
        application.processEvents()


def test_source_id_rename_keeps_both_users_installs_preferences_and_assets(tmp_path, monkeypatch):
    alice = open_context(tmp_path, monkeypatch)
    bob = open_context(tmp_path, monkeypatch, "bob")
    original = SourceDefinition("alpha", "Alpha", "https://github.com/owner/alpha")
    other = SourceDefinition("beta", "Beta", "https://github.com/owner/beta")
    alice.sources.save([original, other])
    for context in (alice, bob):
        for version in ("1.0.0", "2.0.0"):
            install_version(context.paths.installed_slices / "sources" / "alpha" / "tool", "alpha", version)
        install_version(context.paths.installed_slices / "sources" / "beta" / "tool", "beta")
        context.settings.save({"favorites": ["alpha/tool", "beta/tool"], "recently_used": ["beta/tool", "alpha/tool"]})
    for source in (original, other):
        alice.paths.catalog_cache.joinpath(f"{source.id}.json").write_text(
            json.dumps({"revision": "revision", "items": [asdict(catalog_item(source.id))]}), encoding="utf-8"
        )
        assets = alice.paths.slice_assets / "sources" / source.id / "tool" / "1.0.0"
        assets.mkdir(parents=True)
        assets.joinpath("model.bin").write_text(source.id, encoding="utf-8")

    updated = replace(original, id="renamed", name="Renamed")
    backend = SliceManagerBackend(alice)
    backend.update_source(original.id, updated)

    assert alice.sources.load() == [updated, other]
    assert not alice.paths.catalog_cache.joinpath("alpha.json").exists()
    assert {item.key for item in backend.load_cached_catalogs()} == {"renamed/tool", "beta/tool"}
    for context in (alice, bob):
        installed = {item.key: item for item in context.discovery.discover_installed_slices()}
        assert set(installed) == {"renamed/tool", "beta/tool"}
        assert installed["renamed/tool"].version == "2.0.0"
        assert installed["beta/tool"].version == "1.0.0"
        assert context.installer.installed_versions("tool", "renamed") == ["1.0.0", "2.0.0"]
        assert not (context.paths.installed_slices / "sources" / "alpha").exists()
        current = context.paths.installed_slices / "sources" / "renamed" / "tool" / "current.json"
        assert json.loads(current.read_text(encoding="utf-8"))["source_id"] == "renamed"
        assert context.settings.load()["favorites"] == ["renamed/tool", "beta/tool"]
        assert context.settings.load()["recently_used"] == ["beta/tool", "renamed/tool"]
    assert not (alice.paths.slice_assets / "sources" / "alpha").exists()
    for source_id in ("renamed", "beta"):
        assets = alice.paths.slice_assets / "sources" / source_id / "tool" / "1.0.0" / "model.bin"
        assert assets.read_text(encoding="utf-8") == ("alpha" if source_id == "renamed" else "beta")


@pytest.mark.parametrize("rename_during_download", [False, True])
def test_install_publishes_only_while_its_source_still_exists(tmp_path, monkeypatch, rename_during_download):
    context = open_context(tmp_path, monkeypatch)
    original = SourceDefinition("alpha", "Alpha", "https://github.com/owner/alpha")
    context.sources.save([original])
    install_version(context.paths.installed_slices / "sources" / "alpha" / "tool", "alpha")
    package = BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "tool/slice.toml",
            'id="tool"\nname="Tool"\nversion="2.0.0"\ndescription="Updated tool"\n'
            'interface="standard"\noperation="backend:run"',
        )
        archive.writestr("tool/backend.py", "def run(inputs, progress, log): return inputs\n")
    payload = package.getvalue()
    item = replace(catalog_item("alpha", "2.0.0"), sha256=hashlib.sha256(payload).hexdigest())
    backend = SliceManagerBackend(context)
    progress = []

    def download(client, url, report=None):
        assert client.source == original
        assert url == item.download_url
        if report:
            report(100)
        if rename_during_download:
            backend.update_source("alpha", replace(original, id="renamed", name="Renamed"))
        return payload

    monkeypatch.setattr(RemoteRepositoryClient, "download_artifact", download)

    if rename_during_download:
        with pytest.raises(ValueError, match="Source changed during installation"):
            backend.install_catalog_slice(item, progress.append)
        assert not (context.paths.installed_slices / "sources" / "alpha").exists()
        installed = context.discovery.discover_installed_slices()
        assert [(manifest.key, manifest.version) for manifest in installed] == [("renamed/tool", "1.0.0")]
    else:
        backend.install_catalog_slice(item, progress.append)
        installed = context.discovery.discover_installed_slices()
        assert [(manifest.key, manifest.version) for manifest in installed] == [("alpha/tool", "2.0.0")]
        assert context.installer.installed_versions("tool", "alpha") == ["1.0.0", "2.0.0"]
    assert progress == [100]
