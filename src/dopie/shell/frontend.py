from __future__ import annotations

import json
import sys

from PySide6.QtCore import QEvent, QPoint, QProcess, Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dopie import __version__
from dopie.changelog.backend import ChangelogReader
from dopie.changelog.frontend import ChangelogDialog
from dopie.components.tasks import BackgroundTask
from dopie.context import ApplicationContext
from dopie.library.backend import LibraryBackend
from dopie.library.frontend import LibraryPage
from dopie.models import SourceDefinition
from dopie.preferences.backend import PreferencesBackend
from dopie.preferences.frontend import PreferencesDialog
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slice_manager.frontend import SliceManagerPage
from dopie.theme import ThemeController
from dopie.updates.service import ApplicationUpdateService
from dopie.workspace.frontend import WorkspacePage


class MainWindow(QMainWindow):
    def __init__(self, context: ApplicationContext, theme: ThemeController):
        super().__init__()
        self.context = context
        self.theme = theme
        self.thread_pool = QThreadPool.globalInstance()
        self.active_tasks: list[BackgroundTask] = []
        self.vault_lock_timer = QTimer(self)
        self.vault_lock_timer.setSingleShot(True)
        self.vault_lock_timer.timeout.connect(self.context.vault.lock_private_sources)
        QApplication.instance().installEventFilter(self)
        self.setWindowTitle("DoPie")
        self.resize(1180, 760)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        brand = QLabel("DoPie")
        brand.setObjectName("title")
        brand.setContentsMargins(12, 14, 12, 8)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.addItems(["Library", "Favorites", "Slice Manager"])
        self.navigation.currentRowChanged.connect(self.navigate)
        menu_button = QToolButton()
        menu_button.setObjectName("appMenu")
        menu_button.setText("Menu")
        menu_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu_button.setMinimumHeight(40)
        menu_button.setPopupMode(QToolButton.DelayedPopup)
        menu = QMenu(menu_button)
        menu.addAction("Check for updates", lambda: self.check_for_updates(True))
        menu.addAction("What’s New", lambda: self.show_changelog(None))
        menu.addAction("Preferences", self.show_preferences)
        menu.addSeparator()
        menu.addAction("About DoPie", self.show_about)
        menu.addAction("Quit", self.close)
        menu_button.setMenu(menu)
        menu_button.clicked.connect(
            lambda: menu.popup(
                menu_button.mapToGlobal(QPoint(menu_button.width() - menu.sizeHint().width(), menu_button.height()))
            )
        )
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(self.navigation, 1)
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.topbar = QWidget()
        self.topbar.setObjectName("topbar")
        self.topbar.setFixedHeight(58)
        topbar_layout = QHBoxLayout(self.topbar)
        topbar_layout.setContentsMargins(28, 8, 32, 8)
        self.section_title = QLabel("Library")
        self.section_title.setObjectName("sectionTitle")
        self.menu_button = menu_button
        self.menu_button.setText("☰")
        self.menu_button.setAccessibleName("Application menu")
        self.menu_button.setToolTip("Application menu")
        self.menu_button.setFixedSize(40, 40)
        topbar_layout.addWidget(self.section_title)
        topbar_layout.addStretch()
        topbar_layout.addWidget(self.menu_button)
        self.pages = QStackedWidget()
        self.library = LibraryPage(LibraryBackend(context))
        self.favorites = LibraryPage(LibraryBackend(context), favorites_only=True)
        self.manager = SliceManagerPage(SliceManagerBackend(context))
        self.changelog = ChangelogDialog(ChangelogReader(context.paths.changelog), self)
        self.pages.addWidget(self.library)
        self.pages.addWidget(self.favorites)
        self.pages.addWidget(self.manager)
        self.library.open_slice.connect(self.open_slice)
        self.favorites.open_slice.connect(self.open_slice)
        self.library.manage_slice.connect(self.manage_slice)
        self.favorites.manage_slice.connect(self.manage_slice)
        self.library.favorites_changed.connect(self.refresh_libraries)
        self.favorites.favorites_changed.connect(self.refresh_libraries)
        self.manager.library_changed.connect(self.library.refresh)
        self.manager.library_changed.connect(self.favorites.refresh)
        main_layout.addWidget(self.topbar)
        main_layout.addWidget(self.pages, 1)
        layout.addWidget(sidebar)
        layout.addWidget(main, 1)
        self.setCentralWidget(root)
        self.navigation.setCurrentRow(0)
        QTimer.singleShot(0, self.show_changelog_after_update)
        if context.settings.load().get("check_updates_on_launch"):
            QTimer.singleShot(750, lambda: self.check_for_updates(False))
        self.arm_vault_lock()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if event.type() in {QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.TouchBegin}:
            self.arm_vault_lock()
        return super().eventFilter(watched, event)

    def arm_vault_lock(self) -> None:
        minutes = int(self.context.settings.load().get("vault_lock_minutes", 15))
        if minutes:
            self.vault_lock_timer.start(minutes * 60 * 1000)
        else:
            self.vault_lock_timer.stop()

    def navigate(self, index: int) -> None:
        if index >= 0:
            self.section_title.setText(("Library", "Favorites", "Slice Manager")[index])
            self.pages.setCurrentIndex(index)

    def open_slice(self, item: object) -> None:
        self.library.backend.record_slice_opened(item.id)
        self.refresh_libraries()
        self.section_title.setText(item.name)
        workspace = WorkspacePage(
            item.manifest,
            self.context.paths.slice_environments,
            self.context.paths.slice_assets,
            self.context.paths.active_project / "src" / "dopie" / "slices" / "worker.py",
        )
        workspace.close_requested.connect(lambda: self.pages.setCurrentWidget(self.library))
        workspace.close_requested.connect(lambda: self.navigation.setCurrentRow(0))
        self.pages.addWidget(workspace)
        self.pages.setCurrentWidget(workspace)

    def manage_slice(self, item: object) -> None:
        self.navigation.setCurrentRow(2)
        self.manager.tabs.setCurrentWidget(self.manager.available_tab)

    def refresh_libraries(self) -> None:
        self.library.refresh()
        self.favorites.refresh()

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(PreferencesBackend(self.context), self)
        if dialog.exec():
            self.theme.set_mode(str(self.context.settings.load().get("theme", "system")))
            self.arm_vault_lock()
            self.library.refresh()

    def show_changelog(self, previous: str | None) -> None:
        self.changelog.show_releases(previous, __version__)

    def show_changelog_after_update(self) -> None:
        settings = self.context.settings.load()
        if settings.get("last_seen_version") == __version__:
            return
        self.show_changelog(settings.get("last_seen_version"))
        settings["last_seen_version"] = __version__
        self.context.settings.save(settings)

    def check_for_updates(self, interactive: bool = True) -> None:
        settings = self.context.settings.load()
        configured = settings.get("application_update_source", {})
        if not configured.get("repository"):
            if interactive:
                QMessageBox.information(
                    self,
                    "Application updates",
                    "Configure an application repository in Preferences first.",
                )
            return
        source = SourceDefinition.from_dict(configured)
        token = None
        if source.credential:
            if self.context.vault.secrets is None:
                password, accepted = QInputDialog.getText(
                    self,
                    "Unlock private Sources",
                    "Password",
                    QLineEdit.Password,
                )
                if not accepted:
                    return
                try:
                    self.context.vault.unlock_private_sources(password)
                except Exception:
                    QMessageBox.warning(self, "Application updates", "The Source vault could not be unlocked.")
                    return
            token = self.context.vault.source_credential(source.credential)
        state_path = self.context.paths.project / "application" / "current.json"
        installed_revision = None
        if state_path.exists():
            installed_revision = json.loads(state_path.read_text(encoding="utf-8")).get("revision")
        service = ApplicationUpdateService(self.context.paths.updates)
        task = BackgroundTask(lambda: service.check_for_update(source, installed_revision, token))
        task.signals.completed.connect(
            lambda revision: self.application_update_checked(revision, source, token, service, interactive)
        )
        task.signals.failed.connect(
            lambda message: QMessageBox.critical(self, "Update failed", message) if interactive else None
        )
        task.signals.finished.connect(lambda: self.active_tasks.remove(task) if task in self.active_tasks else None)
        self.active_tasks.append(task)
        self.thread_pool.start(task)

    def application_update_checked(
        self,
        revision: str | None,
        source: SourceDefinition,
        token: str | None,
        service: ApplicationUpdateService,
        interactive: bool,
    ) -> None:
        if revision is None:
            if interactive:
                QMessageBox.information(self, "Application updates", "DoPie is up to date.")
            return
        if QMessageBox.question(self, "Update available", "Prepare the latest version now?") != QMessageBox.Yes:
            return
        task = BackgroundTask(lambda: service.prepare_update(source, revision, token))
        task.signals.completed.connect(self.application_update_prepared)
        task.signals.failed.connect(lambda message: QMessageBox.critical(self, "Update failed", message))
        task.signals.finished.connect(lambda: self.active_tasks.remove(task) if task in self.active_tasks else None)
        self.active_tasks.append(task)
        self.thread_pool.start(task)

    def application_update_prepared(self, prepared: dict[str, str]) -> None:
        answer = QMessageBox.question(
            self,
            "Update prepared",
            f"DoPie {prepared['version']} is ready. Restart now?",
        )
        if answer != QMessageBox.Yes:
            return
        root = self.context.paths.project
        if sys.platform == "win32":
            QProcess.startDetached("wscript.exe", [str(root / "Start DoPie.vbs")])
        else:
            QProcess.startDetached(str(root / "start-dopie.sh"), [])
        QApplication.instance().quit()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About DoPie",
            f"DoPie {__version__}\n\nA cross-platform shell for focused Python automation Slices.",
        )
