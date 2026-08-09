from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeColors:
    window: str
    surface: str
    surface_hover: str
    sidebar: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    danger: str


LIGHT = ThemeColors(
    window="#f4f5f7",
    surface="#ffffff",
    surface_hover="#eef1f5",
    sidebar="#e9edf2",
    border="#d5dae1",
    text="#1d2733",
    muted="#657180",
    accent="#356ae6",
    accent_hover="#2858c7",
    accent_text="#ffffff",
    danger="#ba2d36",
)

DARK = ThemeColors(
    window="#15181d",
    surface="#20242b",
    surface_hover="#2a3039",
    sidebar="#1b1f25",
    border="#343b46",
    text="#edf0f4",
    muted="#a5afbd",
    accent="#6d94f7",
    accent_hover="#85a6fa",
    accent_text="#10141a",
    danger="#ff7d86",
)


class ThemeController(QObject):
    theme_changed = Signal(str)

    def __init__(self, application: QApplication, mode: str = "system"):
        super().__init__()
        self.application = application
        self.mode = mode
        QGuiApplication.styleHints().colorSchemeChanged.connect(self.apply_selected_theme)
        self.apply_selected_theme()

    def set_mode(self, mode: str) -> None:
        if mode not in {"system", "light", "dark"}:
            raise ValueError(f"Unsupported theme mode: {mode}")
        self.mode = mode
        self.apply_selected_theme()

    def apply_selected_theme(self) -> None:
        dark = self.mode == "dark" or (
            self.mode == "system" and QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        )
        colors = DARK if dark else LIGHT
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(colors.window))
        palette.setColor(QPalette.WindowText, QColor(colors.text))
        palette.setColor(QPalette.Base, QColor(colors.surface))
        palette.setColor(QPalette.AlternateBase, QColor(colors.surface_hover))
        palette.setColor(QPalette.Text, QColor(colors.text))
        palette.setColor(QPalette.PlaceholderText, QColor(colors.muted))
        palette.setColor(QPalette.Button, QColor(colors.surface))
        palette.setColor(QPalette.ButtonText, QColor(colors.text))
        palette.setColor(QPalette.Highlight, QColor(colors.accent))
        palette.setColor(QPalette.HighlightedText, QColor(colors.accent_text))
        self.application.setPalette(palette)
        self.application.setStyleSheet(
            f"""
            QMainWindow, QDialog, QWidget#page {{ background: {colors.window}; color: {colors.text}; }}
            QWidget#sidebar {{ background: {colors.sidebar}; border-right: 1px solid {colors.border}; }}
            QWidget#topbar {{ background: {colors.surface}; border-bottom: 1px solid {colors.border}; }}
            QLabel#title {{ font-size: 26px; font-weight: 700; }}
            QLabel#sectionTitle {{ font-size: 17px; font-weight: 650; }}
            QLabel#subtitle {{ color: {colors.muted}; }}
            QLabel#cardTitle {{ font-size: 16px; font-weight: 650; }}
            QLabel#muted {{ color: {colors.muted}; }}
            QFrame#card {{ background: {colors.surface}; border: 1px solid {colors.border}; border-radius: 12px; }}
            QFrame#card:hover {{ background: {colors.surface_hover}; border-color: {colors.accent}; }}
            QListWidget#navigation {{ background: transparent; border: none; outline: none; font-size: 15px; }}
            QListWidget#navigation::item {{ border-radius: 8px; padding: 11px; margin: 2px 8px; }}
            QListWidget#navigation::item:selected {{ background: {colors.surface}; color: {colors.text}; }}
            QListWidget#grid {{ background: transparent; border: none; outline: none; }}
            QToolButton#appMenu {{
                background: {colors.surface};
                border: 1px solid {colors.border};
                border-radius: 8px;
                font-size: 22px;
                padding: 3px;
            }}
            QToolButton#appMenu:hover {{ background: {colors.surface_hover}; }}
            QToolButton#appMenu::menu-indicator {{ image: none; }}
            QPushButton {{
                background: {colors.surface};
                border: 1px solid {colors.border};
                border-radius: 7px;
                padding: 7px 13px;
            }}
            QPushButton:hover {{ background: {colors.surface_hover}; }}
            QPushButton#primary {{
                background: {colors.accent};
                color: {colors.accent_text};
                border-color: {colors.accent};
            }}
            QPushButton#primary:hover {{ background: {colors.accent_hover}; }}
            QPushButton#danger {{ color: {colors.danger}; }}
            QToolButton#favoriteButton {{
                background: transparent;
                border: none;
                padding: 0 0 3px 0;
                font-size: 23px;
            }}
            QToolButton#favoriteButton[favorite="false"] {{ color: {colors.muted}; }}
            QToolButton#favoriteButton[favorite="true"] {{ color: {colors.accent}; }}
            QToolButton#favoriteButton:hover {{ background: transparent; color: {colors.accent_hover}; }}
            QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
                background: {colors.surface};
                border: 1px solid {colors.border};
                border-radius: 7px;
                padding: 7px;
            }}
            QComboBox QAbstractItemView {{
                background: {colors.surface};
                color: {colors.text};
                selection-background-color: {colors.surface_hover};
                selection-color: {colors.text};
            }}
            QTabWidget::pane {{ border: 1px solid {colors.border}; background: {colors.surface}; }}
            QTabBar::tab {{ padding: 9px 16px; }}
            QTreeWidget, QTextBrowser {{
                background: {colors.surface};
                border: 1px solid {colors.border};
                border-radius: 8px;
            }}
            QProgressBar {{ border: 1px solid {colors.border}; border-radius: 6px; text-align: center; }}
            QProgressBar::chunk {{ background: {colors.accent}; border-radius: 5px; }}
            """
        )
        self.theme_changed.emit("dark" if dark else "light")
