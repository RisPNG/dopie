from __future__ import annotations

import os
from pathlib import Path

from dopie.paths import AppPaths


def linux_desktop_entry_content(paths: AppPaths) -> str:
    return "\n".join(
        (
            "[Desktop Entry]",
            "Type=Application",
            "Name=DoPie",
            f'Exec="{paths.project / "start-dopie.sh"}"',
            f"Icon={paths.active_project / 'assets' / 'dopie.png'}",
            "Terminal=false",
            "Categories=Utility;Development;",
            "StartupWMClass=DoPie",
            "",
        )
    )


def install_linux_desktop_entry(paths: AppPaths) -> Path:
    applications = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    entry = applications / "dopie.desktop"
    content = linux_desktop_entry_content(paths)
    if not entry.exists() or entry.read_text(encoding="utf-8") != content:
        temporary = entry.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(entry)
    return entry


def remove_linux_desktop_entry(paths: AppPaths) -> None:
    entry = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications" / "dopie.desktop"
    if entry.exists() and entry.read_text(encoding="utf-8") == linux_desktop_entry_content(paths):
        entry.unlink()
