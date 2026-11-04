from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from dopie.context import ApplicationContext
from dopie.models import CatalogSlice, SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import CatalogRefresh, SliceManagerBackend
from dopie.slice_manager.frontend import SliceManagerPage
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import DEFAULT_SHARED_SETTINGS, SettingsStore, SourceStore


def install_fixture(context, source_id, version="1.0.0"):
    root = context.paths.installed_slices / "sources" / source_id / "tool"
    manifest = root / "versions" / version / "slice.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        f'id="tool"\nname="Tool"\nversion="{version}"\ndescription="Tool"\ninterface="standard"\n'
        'operation="backend:run"',
        encoding="utf-8",
    )
    root.joinpath("current.json").write_text(json.dumps({"version": version, "source_id": source_id}), encoding="utf-8")


def select_source(selector, source_id):
    selector.setCurrentIndex(next(index for index in range(selector.count()) if selector.tabData(index) == source_id))


def source_ids(selector):
    return [selector.tabData(index) for index in range(selector.count())]


def available_rows(page):
    return {
        str(page.available.topLevelItem(index).data(0, Qt.UserRole)): page.available.topLevelItem(index).text(4)
        for index in range(page.available.topLevelItemCount())
    }


def installed_keys(page):
    return {
        page.installed.topLevelItem(index).data(0, Qt.UserRole).key
        for index in range(page.installed.topLevelItemCount())
    }


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    application = QApplication.instance() or QApplication([])
    paths = resolve_app_paths()
    context = ApplicationContext(
        paths,
        SettingsStore(paths.settings),
        SettingsStore(paths.shared_settings, DEFAULT_SHARED_SETTINGS),
        SourceStore(paths.sources),
        VaultStore(paths.vault, paths.vault_key),
        SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        SliceInstaller(paths.installed_slices),
    )
    context.sources.save(
        [
            SourceDefinition("first", "First Source", "https://github.com/example/first"),
            SourceDefinition("second", "Second Source", "https://github.com/example/second"),
            SourceDefinition("hidden", "Hidden Source", "https://github.com/example/hidden", enabled=False),
        ]
    )
    bundled = paths.bundled_slices / "tool" / "slice.toml"
    bundled.parent.mkdir(parents=True)
    bundled.write_text(
        'id="tool"\nname="Bundled tool"\nversion="1.0.0"\ndescription="Bundled"\ninterface="standard"\n'
        'operation="backend:run"',
        encoding="utf-8",
    )
    install_fixture(context, "first")
    install_fixture(context, "hidden")
    for source_id, version in (("first", "2.0.0"), ("second", "1.0.0"), ("hidden", "1.0.0")):
        item = CatalogSlice(
            "tool",
            "Tool",
            version,
            "Tool",
            "Other",
            "Testing",
            "MIT",
            "https://example.test/tool.zip",
            "0" * 64,
            source_id,
        )
        context.available.append(item)
        paths.catalog_cache.joinpath(f"{source_id}.json").write_text(
            json.dumps({"revision": "revision", "items": [asdict(item)]}), encoding="utf-8"
        )
    manager = SliceManagerPage(SliceManagerBackend(context))
    yield manager
    manager.close()
    application.processEvents()


def test_source_tabs_filter_installed_and_available_independently(page, monkeypatch):
    assert source_ids(page.installed_sources) == [None, "@bundled", "first", "second"]
    assert source_ids(page.available_sources) == [None, "first", "second"]
    assert installed_keys(page) == {"tool", "first/tool", "hidden/tool"}
    assert available_rows(page) == {"first/tool": "Update available", "second/tool": "Available"}

    select_source(page.installed_sources, "first")
    select_source(page.available_sources, "second")
    assert installed_keys(page) == {"first/tool"}
    assert available_rows(page) == {"second/tool": "Available"}
    assert page.catalog_status.text() == "1 Slices available"
    page.available.setCurrentItem(page.available.topLevelItem(0))
    requested = []
    monkeypatch.setattr(page, "install_slice", requested.append)
    page.install_selected()
    assert [item.key for item in requested] == ["second/tool"]

    install_fixture(page.backend.context, "second")
    page.refresh_installed()
    page.catalog_refreshed(CatalogRefresh(tuple(page.backend.context.available), ()))
    assert available_rows(page) == {"second/tool": "Installed"}
    assert page.installed_sources.tabData(page.installed_sources.currentIndex()) == "first"
    assert installed_keys(page) == {"first/tool"}
    select_source(page.installed_sources, "@bundled")
    assert installed_keys(page) == {"tool"}


def test_source_tabs_follow_enable_disable_and_preserve_other_selections(page, monkeypatch):
    select_source(page.installed_sources, "first")
    select_source(page.available_sources, "first")
    refreshed = []
    monkeypatch.setattr(page, "refresh_available", refreshed.append)

    page.source_enabled_changed("first", False)

    assert source_ids(page.installed_sources) == [None, "@bundled", "second"]
    assert source_ids(page.available_sources) == [None, "second"]
    assert page.installed_sources.currentIndex() == 0
    assert installed_keys(page) == {"tool", "first/tool", "hidden/tool"}
    assert available_rows(page) == {"second/tool": "Available"}

    select_source(page.available_sources, "second")
    page.source_enabled_changed("first", True)
    assert refreshed == [{"first"}]
    assert source_ids(page.available_sources) == [None, "first", "second"]
    assert page.available_sources.tabData(page.available_sources.currentIndex()) == "second"
    assert available_rows(page) == {"second/tool": "Available"}


def test_source_tabs_follow_source_changes_and_refresh_without_network(page, monkeypatch):
    select_source(page.installed_sources, "first")
    select_source(page.available_sources, "first")
    monkeypatch.setattr(page, "refresh_available", lambda *args: pytest.fail("Unexpected network refresh"))
    source = page.backend.context.sources.load()[0]
    page.backend.update_source("first", replace(source, name="Renamed Source"))
    page.backend.add_source(SourceDefinition("third", "Third Source", "https://github.com/example/third"))
    page.refresh_sources()

    assert page.installed_sources.tabText(page.installed_sources.currentIndex()) == "Renamed Source"
    assert page.available_sources.tabText(page.available_sources.currentIndex()) == "Renamed Source"
    assert source_ids(page.available_sources) == [None, "first", "second", "third"]
    assert available_rows(page) == {"first/tool": "Update available"}
    page.catalog_refreshed(CatalogRefresh(tuple(page.backend.context.available), ()))
    assert page.available_sources.tabData(page.available_sources.currentIndex()) == "first"

    page.backend.remove_source("first")
    page.refresh_sources()
    page.catalog_refreshed(CatalogRefresh(tuple(page.backend.context.available), ()))
    assert source_ids(page.available_sources) == [None, "second", "third"]
    assert page.available_sources.currentIndex() == 0
    assert available_rows(page) == {"second/tool": "Available"}
    assert "first/tool" in installed_keys(page)


def test_source_tabs_support_empty_sources_and_source_less_installs(page):
    context = page.backend.context
    context.sources.save([])
    local = context.paths.installed_slices / "manual" / "slice.toml"
    local.parent.mkdir()
    local.write_text(
        'id="manual"\nname="Manual"\nversion="1.0.0"\ndescription="Manual"\ninterface="standard"\n'
        'operation="backend:run"',
        encoding="utf-8",
    )
    page.refresh_sources()

    assert source_ids(page.available_sources) == [None]
    assert available_rows(page) == {}
    assert source_ids(page.installed_sources) == [None, "@bundled", "@local"]
    select_source(page.installed_sources, "@local")
    assert installed_keys(page) == {"manual"}


def test_catalog_refresh_updates_tabs_changed_by_another_user(page):
    select_source(page.installed_sources, "first")
    select_source(page.available_sources, "first")
    page.backend.set_source_enabled("first", False)

    page.catalog_refreshed(CatalogRefresh(page.backend.load_cached_catalogs(), ()))

    assert page.installed_sources.currentIndex() == 0
    assert installed_keys(page) == {"tool", "first/tool", "hidden/tool"}
    assert page.available_sources.currentIndex() == 0
    assert available_rows(page) == {"second/tool": "Available"}


def test_installation_progress_uses_the_selected_source_identity(page, monkeypatch):
    started = []
    progress_updates = []
    page.slice_installation_started.connect(started.append)
    page.slice_installation_progress.connect(lambda key, percent: progress_updates.append((key, percent)))
    monkeypatch.setattr(page.backend, "install_catalog_slice", lambda item, progress: progress(55))

    page.install_slice(page.available_items["second/tool"])
    page.thread_pool.waitForDone()
    QApplication.instance().processEvents()

    assert started == ["second/tool"]
    assert progress_updates == [("second/tool", 55)]
    assert not page.active_tasks


def test_rollback_uses_the_selected_source_identity(page, monkeypatch):
    select_source(page.installed_sources, "first")
    page.installed.setCurrentItem(page.installed.topLevelItem(0))
    requested_versions = []
    rollbacks = []
    monkeypatch.setattr(
        page.backend.context.installer,
        "installed_versions",
        lambda slice_id, source_id: requested_versions.append((slice_id, source_id)) or ["1.0.0", "0.9.0"],
    )
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args, **kwargs: ("0.9.0", True))
    monkeypatch.setattr(
        page.backend, "rollback_slice", lambda manifest, version: rollbacks.append((manifest.key, version))
    )

    page.rollback_selected()

    assert requested_versions == [("tool", "first")]
    assert rollbacks == [("first/tool", "0.9.0")]
