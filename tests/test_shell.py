from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractItemView, QApplication

from dopie.context import ApplicationContext, VaultSession
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.shell.frontend import MainWindow
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore
from dopie.theme import ThemeController


def test_shell_builds_all_primary_pages_offscreen(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    (tmp_path / "portable.toml").write_text('mode="portable"', encoding="utf-8")
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
    (tmp_path / "changelog").mkdir()
    paths = resolve_app_paths()
    context = ApplicationContext(
        paths,
        SettingsStore(paths.settings),
        SourceStore(paths.sources),
        VaultSession(VaultStore(paths.vault)),
        SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        SliceInstaller(paths.installed_slices),
    )
    context.settings.save({"theme": "system", "last_seen_version": "0.1.0"})
    application = QApplication.instance() or QApplication([])

    window = MainWindow(context, ThemeController(application, "system"))

    assert window.navigation.count() == 3
    assert window.pages.count() == 3
    assert window.pages.indexOf(window.changelog) == -1
    assert window.library.grid.selectionMode() == QAbstractItemView.NoSelection
    assert window.topbar.parent() is not None
    assert window.menu_button.parent() is window.topbar
    assert window.menu_button.text() == "☰"
    assert window.menu_button.menu() is not None
    assert window.vault_lock_timer.isActive()
    window.show()
    application.processEvents()
    window.menu_button.click()
    application.processEvents()
    assert (
        window.menu_button.menu().geometry().right()
        <= window.menu_button.mapToGlobal(QPoint(window.menu_button.width(), 0)).x()
    )
    window.menu_button.menu().hide()
    window.open_slice(window.library.backend.build_library()[0])
    workspace = window.pages.currentWidget()
    workspace.close_requested.emit()
    assert window.pages.currentWidget() is window.library
    assert window.navigation.currentRow() == 0
    window.close()
