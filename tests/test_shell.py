from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QLabel, QMessageBox

from dopie.components.frontend import IconCheckBox
from dopie.context import ApplicationContext, VaultSession
from dopie.models import CatalogSlice, SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.preferences.backend import PreferencesBackend
from dopie.preferences.frontend import PreferencesDialog
from dopie.security.vault import VaultStore
from dopie.shell.frontend import MainWindow
from dopie.slice_manager.backend import CatalogRefresh
from dopie.slice_manager.frontend import DeselectableTreeWidget
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore
from dopie.theme import ThemeController


def test_shell_builds_all_primary_pages_offscreen(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    bundled = tmp_path / "slices" / "local"
    bundled.mkdir(parents=True)
    bundled.joinpath("slice.toml").write_text(
        'id="local"\nname="Local"\nversion="1.0.0"\ndescription="Local"\ninterface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    bundled.joinpath("backend.py").write_text(
        "def run(inputs, progress, log): return inputs\n",
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    shutil.copy2(
        Path(__file__).parents[1] / "application" / "base" / "assets" / "dopie.png",
        assets / "dopie.png",
    )
    (tmp_path / "changelog").mkdir()
    paths = resolve_app_paths()
    context = ApplicationContext(
        paths,
        SettingsStore(paths.settings),
        SourceStore(paths.sources),
        VaultSession(VaultStore(paths.vault, paths.vault_key)),
        SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        SliceInstaller(paths.installed_slices),
    )
    context.settings.save({"theme": "system", "last_seen_version": "1.1.1"})
    context.sources.save(
        [SourceDefinition("community", "Community", "https://github.com/example/community")]
    )
    application = QApplication.instance() or QApplication([])

    window = MainWindow(context, ThemeController(application, "system"))

    assert window.navigation.count() == 3
    assert window.pages.count() == 3
    assert window.pages.indexOf(window.changelog) == -1
    assert window.library.grid.selectionMode() == QAbstractItemView.NoSelection
    for table in (window.manager.installed, window.manager.available, window.manager.sources):
        assert table.selectionBehavior() == QAbstractItemView.SelectRows
        assert table.header().sectionResizeMode(0) == QHeaderView.Interactive
        assert table.header().stretchLastSection()
    source_enabled = window.manager.sources.itemWidget(window.manager.sources.topLevelItem(0), 0)
    assert isinstance(window.manager.sources, DeselectableTreeWidget)
    assert isinstance(source_enabled, IconCheckBox)
    assert source_enabled.text() == "Community"
    assert source_enabled.isChecked()
    assert not source_enabled.icon().isNull()
    assert source_enabled.focusPolicy() == Qt.NoFocus
    assert window.manager.sources.columnWidth(0) >= source_enabled.sizeHint().width()
    source_width = window.manager.sources.columnWidth(0) + 40
    window.manager.sources.setColumnWidth(0, source_width)
    assert window.manager.sources.columnWidth(0) == source_width
    source_enabled.click()
    assert not context.sources.load()[0].enabled
    window.manager.catalog_refreshed(
        CatalogRefresh(
            (
                CatalogSlice(
                    "local",
                    "Local",
                    "1.0.0",
                    "Local",
                    "Other",
                    "Test",
                    "MIT",
                    "https://example.test/local.zip",
                    "0" * 64,
                    "community",
                ),
            ),
            (),
        )
    )
    available_row = window.manager.available.topLevelItem(0)
    assert available_row.text(4) == "Installed"
    assert not available_row.isDisabled()
    window.manager.available.setCurrentItem(available_row)
    window.manager.install_selected()
    assert window.manager.active_tasks == []
    assert window.topbar.parent() is not None
    assert not window.findChild(QLabel, "brandIcon").pixmap().isNull()
    assert window.menu_button.parent() is window.topbar
    assert window.menu_button.text() == "☰"
    assert window.menu_button.menu() is not None
    about_message = []
    monkeypatch.setattr(
        QMessageBox,
        "about",
        lambda parent, title, message: about_message.append((parent, title, message)),
    )
    window.show_about()
    assert about_message[0][1] == "About DoPie"
    assert "MIT License" in about_message[0][2]
    assert "Copyright © 2026 Ris" in about_message[0][2]
    window.show()
    application.processEvents()
    window.manager.tabs.setCurrentWidget(window.manager.sources_tab)
    source_row = window.manager.sources.topLevelItem(0)
    window.manager.sources.setCurrentItem(source_row)
    QTest.mouseClick(
        window.manager.sources.viewport(),
        Qt.LeftButton,
        pos=QPoint(5, window.manager.sources.viewport().height() - 5),
    )
    assert window.manager.sources.currentItem() is None
    window.menu_button.click()
    application.processEvents()
    assert (
        window.menu_button.menu().geometry().right()
        <= window.menu_button.mapToGlobal(QPoint(window.menu_button.width(), 0)).x()
    )
    window.menu_button.menu().hide()
    preferences = PreferencesDialog(PreferencesBackend(context), window)
    assert isinstance(preferences.include_available, IconCheckBox)
    assert isinstance(preferences.check_updates, IconCheckBox)
    assert not hasattr(preferences, "public_key")
    assert not hasattr(preferences, "vault_password")
    assert not hasattr(preferences, "confirm_vault_password")
    preferences.close()
    window.open_slice(window.library.backend.build_library()[0])
    workspace = window.pages.currentWidget()
    workspace.close_requested.emit()
    assert window.pages.currentWidget() is window.library
    assert window.navigation.currentRow() == 0
    window.close()
