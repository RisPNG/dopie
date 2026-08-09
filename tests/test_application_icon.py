from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from dopie.desktop import install_linux_desktop_entry, remove_linux_desktop_entry
from dopie.paths import resolve_app_paths


def test_application_logo_is_a_valid_qt_icon(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "application" / "base" / "assets" / "dopie.png"
    windows_icon = logo.with_suffix(".ico")

    assert application is not None
    assert logo.is_file()
    assert not QIcon(str(logo)).isNull()
    assert windows_icon.is_file()
    assert not QIcon(str(windows_icon)).isNull()
    application_source = logo.parents[1] / "src" / "dopie" / "application.py"
    windows_integration = application_source.read_text(encoding="utf-8")
    assert "LoadImageW" in windows_integration
    assert "SendMessageW" in windows_integration
    assert "0x0080" in windows_integration


def test_linux_desktop_entry_uses_portable_launcher_and_logo(tmp_path, monkeypatch):
    monkeypatch.delenv("DOPIE_ROOT", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths = resolve_app_paths()

    entry = install_linux_desktop_entry(paths)
    content = entry.read_text(encoding="utf-8")

    assert f'Exec="{paths.project / "start-dopie.sh"}"' in content
    assert f"Icon={paths.active_project / 'assets' / 'dopie.png'}" in content
    assert "StartupWMClass=DoPie" in content

    remove_linux_desktop_entry(paths)

    assert not entry.exists()
