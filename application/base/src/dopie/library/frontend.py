from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dopie.library.backend import LibraryBackend, LibraryItem


class SliceCard(QFrame):
    activated = Signal(object)
    favorite_changed = Signal(str, bool)
    update_requested = Signal(object)

    def __init__(self, item: LibraryItem):
        super().__init__()
        self.item = item
        self.setObjectName("card")
        self.setFixedSize(280, 166)
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = QLabel(item.name)
        title.setObjectName("cardTitle")
        version = QLabel(item.version)
        version.setObjectName("muted")
        heading.addWidget(title)
        heading.setAlignment(title, Qt.AlignVCenter)
        if item.installed:
            favorite = QToolButton()
            favorite.setText("★" if item.favorite else "☆")
            favorite.setToolButtonStyle(Qt.ToolButtonTextOnly)
            favorite.setObjectName("favoriteButton")
            favorite.setProperty("favorite", item.favorite)
            favorite.setAccessibleName("Remove from Favorites" if item.favorite else "Add to Favorites")
            favorite.setToolTip("Remove from Favorites" if item.favorite else "Add to Favorites")
            favorite.setFixedSize(30, 30)
            favorite.clicked.connect(lambda: self.favorite_changed.emit(item.id, not item.favorite))
            heading.addWidget(favorite)
            heading.setAlignment(favorite, Qt.AlignVCenter)
        heading.addStretch()
        heading.addWidget(version)
        description = QLabel(item.description)
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignTop)
        category = QLabel(item.category)
        category.setObjectName("muted")
        actions = QHBoxLayout()
        actions.addStretch()
        action = QPushButton("Open" if item.installed else "Install")
        if item.update is None:
            action.setObjectName("primary")
        action.clicked.connect(lambda: self.activated.emit(self.item))
        actions.addWidget(action)
        if item.update is not None:
            self.update_button = QPushButton("Update")
            self.update_button.setObjectName("primary")
            self.update_button.setToolTip(f"Update to {item.update.version}")
            self.update_button.clicked.connect(
                lambda: (
                    self.update_button.setText("Updating…"),
                    self.update_button.setEnabled(False),
                    self.update_requested.emit(item.update),
                )
            )
            self.update_progress = QProgressBar()
            self.update_progress.setRange(0, 0)
            self.update_progress.setTextVisible(True)
            self.update_progress.setFixedWidth(104)
            self.update_progress.setVisible(False)
            actions.addWidget(self.update_progress)
            actions.addWidget(self.update_button)
        layout.addLayout(heading)
        layout.addWidget(description, 1)
        layout.addWidget(category)
        layout.addLayout(actions)


class LibraryPage(QWidget):
    open_slice = Signal(object)
    manage_slice = Signal(object)
    update_slice = Signal(object)
    favorites_changed = Signal()

    def __init__(self, backend: LibraryBackend, favorites_only: bool = False):
        super().__init__()
        self.backend = backend
        self.favorites_only = favorites_only
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Slices")
        self.search.textChanged.connect(self.refresh)
        self.grid = QListWidget()
        self.grid.setObjectName("grid")
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.grid.setFocusPolicy(Qt.NoFocus)
        self.grid.setSpacing(14)
        self.empty = QLabel(
            "Favorite Slices will appear here." if favorites_only else "Installed Slices will appear here."
        )
        self.empty.setObjectName("subtitle")
        self.empty.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.search)
        layout.addWidget(self.grid, 1)
        layout.addWidget(self.empty, 1)
        self.refresh()

    def refresh(self) -> None:
        items = self.backend.build_library(self.search.text(), self.favorites_only)
        self.grid.clear()
        self.grid.setVisible(bool(items))
        self.empty.setVisible(not items)
        for item in items:
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(294, 180))
            card = SliceCard(item)
            card.activated.connect(self.open_slice if item.installed else self.manage_slice)
            card.favorite_changed.connect(self.change_favorite)
            card.update_requested.connect(self.update_slice)
            self.grid.addItem(list_item)
            self.grid.setItemWidget(list_item, card)

    def show_update_progress(self, slice_id: str, percent: int | None = None) -> None:
        for index in range(self.grid.count()):
            card = self.grid.itemWidget(self.grid.item(index))
            if card.item.id != slice_id or not hasattr(card, "update_progress"):
                continue
            card.update_button.setVisible(False)
            card.update_progress.setVisible(True)
            if percent is not None:
                card.update_progress.setRange(0, 100)
                card.update_progress.setValue(percent)

    def change_favorite(self, slice_id: str, favorite: bool) -> None:
        self.backend.set_slice_favorite(slice_id, favorite)
        self.favorites_changed.emit()
