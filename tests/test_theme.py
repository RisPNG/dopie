from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from dopie.theme import DARK, LIGHT, ThemeController


def test_light_and_dark_modes_apply_central_palette(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    controller = ThemeController(application, "light")

    assert application.palette().window().color() == QColor(LIGHT.window)

    controller.set_mode("dark")

    assert application.palette().window().color() == QColor(DARK.window)
    assert application.palette().placeholderText().color() == QColor(DARK.muted)
    assert f"selection-color: {DARK.text}" in application.styleSheet()
