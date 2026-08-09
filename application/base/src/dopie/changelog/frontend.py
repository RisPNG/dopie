from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from dopie.changelog.backend import ChangelogReader


class ChangelogDialog(QDialog):
    def __init__(self, reader: ChangelogReader, parent: QWidget | None = None):
        super().__init__(parent)
        self.reader = reader
        self.setWindowTitle("What’s New in DoPie")
        self.resize(620, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(self.notes, 1)
        layout.addWidget(buttons)

    def show_releases(self, previous: str | None, current: str) -> None:
        self.notes.setMarkdown(self.reader.release_notes_since(previous, current))
        self.exec()
