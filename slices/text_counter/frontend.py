from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from .backend import analyze_text


class SliceWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Paste or type text here")
        self.summary = QLabel("0 words · 0 characters · 0 lines")
        self.summary.setObjectName("subtitle")
        self.editor.textChanged.connect(self.refresh_statistics)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.summary)

    def refresh_statistics(self) -> None:
        statistics = analyze_text(self.editor.toPlainText())
        self.summary.setText(
            f"{statistics.words} words · {statistics.characters} characters · {statistics.lines} lines"
        )
