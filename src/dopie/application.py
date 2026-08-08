from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from dopie.context import ApplicationContext, VaultSession
from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.shell.frontend import MainWindow
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore
from dopie.theme import ThemeController


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("DoPie")
    application.setOrganizationName("DoPie")
    paths = resolve_app_paths()
    settings = SettingsStore(paths.settings)
    theme = ThemeController(application, str(settings.load().get("theme", "system")))
    context = ApplicationContext(
        paths=paths,
        settings=settings,
        sources=SourceStore(paths.sources),
        vault=VaultSession(VaultStore(paths.vault)),
        discovery=SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        installer=SliceInstaller(paths.installed_slices),
    )
    window = MainWindow(context, theme)
    window.show()
    marker = os.environ.get("DOPIE_STARTUP_MARKER")
    if marker:
        QTimer.singleShot(0, lambda: Path(marker).write_text("healthy", encoding="utf-8"))
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
