from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QToolButton


class IconCheckBox(QToolButton):
    def __init__(self, label: str, checked: bool = False):
        super().__init__()
        self.setObjectName("iconCheckBox")
        self.setText(label)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(18, 18))
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.NoFocus)
        self.toggled.connect(lambda _: self.sync_state_icon())
        self.sync_state_icon()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            self.sync_state_icon()

    def sync_state_icon(self) -> None:
        pixmap = QPixmap(self.iconSize())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self.palette().color(QPalette.ButtonText)
        painter.setPen(QPen(color, 1.8))
        square = QRectF(2.5, 3.5, 13, 13)
        if self.isChecked():
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(square, 1.5, 1.5)
        else:
            painter.drawRoundedRect(square, 1.5, 1.5)
        painter.end()
        self.setIcon(QIcon(pixmap))
