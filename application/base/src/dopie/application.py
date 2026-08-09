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

        windll.shell32.SetCurrentProcessExplicitAppUserModelID("RisPNG.DoPie")
    application = QApplication(sys.argv)
    application.setApplicationName("DoPie")
    application.setOrganizationName("DoPie")
    application.setDesktopFileName("dopie")
    paths = resolve_app_paths()
    if sys.platform.startswith("linux"):
        remove_linux_desktop_entry(paths)
        install_linux_desktop_entry(paths)
        application.aboutToQuit.connect(lambda: remove_linux_desktop_entry(paths))
    application_icon = QIcon(
        str(paths.active_project / "assets" / ("dopie.ico" if sys.platform == "win32" else "dopie.png"))
    )
    application.setWindowIcon(application_icon)
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
    window.setWindowIcon(application_icon)
    window.show()
    if sys.platform == "win32":
        from ctypes import WinDLL, c_ssize_t, get_last_error, wintypes

        user32 = WinDLL("user32", use_last_error=True)
        user32.LoadImageW.argtypes = (
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            wintypes.INT,
            wintypes.INT,
            wintypes.UINT,
        )
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.SendMessageW.restype = c_ssize_t
        icon_path = str(paths.active_project / "assets" / "dopie.ico")
        large_icon = user32.LoadImageW(None, icon_path, 1, 256, 256, 0x10)
        small_icon = user32.LoadImageW(None, icon_path, 1, 32, 32, 0x10)
        if not large_icon or not small_icon:
            raise OSError(get_last_error(), f"Could not load the Windows application icon: {icon_path}")
        window_handle = int(window.winId())
        user32.SendMessageW(window_handle, 0x0080, 1, large_icon)
        user32.SendMessageW(window_handle, 0x0080, 0, small_icon)
    marker = os.environ.get("DOPIE_STARTUP_MARKER")
    if marker:
        QTimer.singleShot(5000, lambda: Path(marker).write_text("healthy", encoding="utf-8"))
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
