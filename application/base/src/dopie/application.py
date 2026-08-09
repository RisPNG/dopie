from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from dopie.context import ApplicationContext, VaultSession
from dopie.desktop import install_linux_desktop_entry, remove_linux_desktop_entry
from dopie.paths import resolve_app_paths
from dopie.provisioning.backend import ProvisioningBackend
from dopie.provisioning.frontend import provision_portable_copy
from dopie.security.vault import VaultStore
from dopie.shell.frontend import MainWindow
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore
from dopie.theme import ThemeController


def main() -> int:
    if sys.platform == "win32":
        from ctypes import windll

        windll.shell32.SetCurrentProcessExplicitAppUserModelID("DoPie.DoPie")
    application = QApplication(sys.argv)
    application.setApplicationName("DoPie")
    application.setOrganizationName("DoPie")
    application.setDesktopFileName("dopie")
    paths = resolve_app_paths()
    if sys.platform.startswith("linux"):
        remove_linux_desktop_entry(paths)
        install_linux_desktop_entry(paths)
        application.aboutToQuit.connect(lambda: remove_linux_desktop_entry(paths))
    application.setWindowIcon(QIcon(str(paths.active_project / "assets" / "dopie.png")))
    settings = SettingsStore(paths.settings)
    theme = ThemeController(application, str(settings.load().get("theme", "system")))
    context = ApplicationContext(
        paths=paths,
        settings=settings,
        sources=SourceStore(paths.sources),
        vault=VaultSession(VaultStore(paths.vault, paths.vault_key)),
        discovery=SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        installer=SliceInstaller(paths.installed_slices),
    )
    provision_portable_copy(ProvisioningBackend(paths))
    SliceManagerBackend(context).load_cached_catalogs()
    window = MainWindow(context, theme)
    window.show()
    marker = os.environ.get("DOPIE_STARTUP_MARKER")
    if marker:
        QTimer.singleShot(5000, lambda: Path(marker).write_text("healthy", encoding="utf-8"))
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
