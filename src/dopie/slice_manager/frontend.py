from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dopie.components.tasks import BackgroundTask
from dopie.models import CatalogSlice, SourceDefinition
from dopie.slice_manager.backend import CatalogRefresh, SliceManagerBackend
from dopie.slices.compatibility import evaluate_slice_compatibility
from dopie.sources.profile import PortableProfileService


class SourceDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Source")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.source_id = QLineEdit()
        self.name = QLineEdit()
        self.provider = QComboBox()
        self.provider.addItems(["GitHub", "Forgejo"])
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("Required for Forgejo")
        self.repository = QLineEdit()
        self.repository.setPlaceholderText("owner/repository")
        self.reference = QLineEdit("main")
        self.index = QLineEdit("index.json")
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.public_key = QLineEdit()
        self.public_key.setPlaceholderText("Optional base64 Ed25519 public key")
        form.addRow("Source ID", self.source_id)
        form.addRow("Name", self.name)
        form.addRow("Provider", self.provider)
        form.addRow("Base URL", self.base_url)
        form.addRow("Repository", self.repository)
        form.addRow("Branch", self.reference)
        form.addRow("Index", self.index)
        form.addRow("Access token", self.token)
        form.addRow("Signing key", self.public_key)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def source_definition(self) -> SourceDefinition:
        token = self.token.text().strip()
        source_id = self.source_id.text().strip()
        return SourceDefinition(
            id=source_id,
            name=self.name.text().strip(),
            provider=self.provider.currentText().casefold(),
            base_url=self.base_url.text().strip() or None,
            repository=self.repository.text().strip(),
            reference=self.reference.text().strip(),
            index=self.index.text().strip(),
            credential=f"source:{source_id}" if token else None,
            public_key=self.public_key.text().strip() or None,
        )


class SliceManagerPage(QWidget):
    library_changed = Signal()

    def __init__(self, backend: SliceManagerBackend):
        super().__init__()
        self.backend = backend
        self.available_items: dict[str, CatalogSlice] = {}
        self.thread_pool = QThreadPool.globalInstance()
        self.active_tasks: list[BackgroundTask] = []
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        subtitle = QLabel("Install Slices and manage the Sources you trust.")
        subtitle.setObjectName("subtitle")
        self.tabs = QTabWidget()
        self.installed_tab = QWidget()
        self.available_tab = QWidget()
        self.sources_tab = QWidget()
        self.tabs.addTab(self.installed_tab, "Installed")
        self.tabs.addTab(self.available_tab, "Available")
        self.tabs.addTab(self.sources_tab, "Sources")
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs, 1)
        self._build_installed_tab()
        self._build_available_tab()
        self._build_sources_tab()
        self.refresh_installed()
        self.refresh_sources()

    def _build_installed_tab(self) -> None:
        layout = QVBoxLayout(self.installed_tab)
        self.installed = QTreeWidget()
        self.installed.setHeaderLabels(["Slice", "Version", "Category", "Origin"])
        remove = QPushButton("Uninstall selected")
        remove.setObjectName("danger")
        remove.clicked.connect(self.uninstall_selected)
        rollback = QPushButton("Roll back selected")
        rollback.clicked.connect(self.rollback_selected)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(rollback)
        actions.addWidget(remove)
        layout.addWidget(self.installed)
        layout.addLayout(actions)

    def _build_available_tab(self) -> None:
        layout = QVBoxLayout(self.available_tab)
        toolbar = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Sources")
        self.refresh_button.clicked.connect(self.refresh_available)
        install = QPushButton("Install selected")
        install.setObjectName("primary")
        install.clicked.connect(self.install_selected)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch()
        toolbar.addWidget(install)
        self.catalog_status = QLabel("")
        self.catalog_status.setObjectName("subtitle")
        self.available = QTreeWidget()
        self.available.setHeaderLabels(["Slice", "Version", "Category", "Source", "Status"])
        layout.addLayout(toolbar)
        layout.addWidget(self.catalog_status)
        layout.addWidget(self.available)

    def _build_sources_tab(self) -> None:
        layout = QVBoxLayout(self.sources_tab)
        toolbar = QHBoxLayout()
        add = QPushButton("Add Source")
        add.setObjectName("primary")
        add.clicked.connect(self.add_source)
        remove = QPushButton("Remove selected")
        remove.setObjectName("danger")
        remove.clicked.connect(self.remove_source)
        lock = QPushButton("Lock private Sources")
        lock.clicked.connect(self.lock_sources)
        export_profile = QPushButton("Export Profile")
        export_profile.clicked.connect(self.export_profile)
        import_profile = QPushButton("Import Profile")
        import_profile.clicked.connect(self.import_profile)
        toolbar.addWidget(add)
        toolbar.addWidget(remove)
        toolbar.addWidget(export_profile)
        toolbar.addWidget(import_profile)
        toolbar.addStretch()
        toolbar.addWidget(lock)
        self.sources = QTreeWidget()
        self.sources.setHeaderLabels(["Source", "Provider", "Repository", "Branch", "Access"])
        self.sources.itemChanged.connect(self.source_enabled_changed)
        layout.addLayout(toolbar)
        layout.addWidget(self.sources)

    def _ensure_private_sources_unlocked(self, create: bool = False) -> bool:
        if self.backend.context.vault.secrets is not None:
            return True
        title = "Create Source vault" if create else "Unlock private Sources"
        password, accepted = QInputDialog.getText(self, title, "Password", QLineEdit.Password)
        if not accepted or not password:
            return False
        try:
            if create:
                confirmation, confirmed = QInputDialog.getText(self, title, "Confirm password", QLineEdit.Password)
                if not confirmed or confirmation != password:
                    QMessageBox.warning(self, title, "Passwords do not match.")
                    return False
                self.backend.context.vault.create_private_source_vault(password)
            else:
                self.backend.context.vault.unlock_private_sources(password)
        except Exception:
            QMessageBox.warning(self, title, "The vault could not be unlocked.")
            return False
        return True

    def refresh_installed(self) -> None:
        self.installed.clear()
        for manifest in self.backend.installed_slices():
            origin = "Installed" if manifest.origin == "installed" else "Bundled"
            row = QTreeWidgetItem([manifest.name, manifest.version, manifest.category, origin])
            row.setData(0, Qt.UserRole, manifest)
            self.installed.addTopLevelItem(row)

    def refresh_available(self) -> None:
        if any(source.credential for source in self.backend.context.sources.load()):
            if not self._ensure_private_sources_unlocked():
                return
        self.refresh_button.setEnabled(False)
        self.catalog_status.setText("Refreshing Sources…")
        task = BackgroundTask(self.backend.refresh_source_catalogs)
        task.signals.completed.connect(self.catalog_refreshed)
        task.signals.failed.connect(lambda message: QMessageBox.critical(self, "Source refresh failed", message))
        task.signals.finished.connect(lambda: self.refresh_button.setEnabled(True))
        task.signals.finished.connect(lambda: self.active_tasks.remove(task) if task in self.active_tasks else None)
        self.active_tasks.append(task)
        self.thread_pool.start(task)

    def catalog_refreshed(self, refresh: CatalogRefresh) -> None:
        items = refresh.items
        self.available.clear()
        self.available_items = {item.id: item for item in items}
        installed = {item.id: item for item in self.backend.installed_slices()}
        for item in items:
            compatibility = evaluate_slice_compatibility(item)
            if item.id not in installed:
                status = "Available"
            elif self.backend.slice_update_available(item, installed):
                status = "Update available"
            else:
                status = "Installed"
            if not compatibility.compatible:
                status = compatibility.reason
            row = QTreeWidgetItem([item.name, item.version, item.category, item.source_id, status])
            row.setData(0, Qt.UserRole, item.id)
            if (item.id in installed and status != "Update available") or not compatibility.compatible:
                row.setDisabled(True)
            self.available.addTopLevelItem(row)
        if refresh.errors:
            self.catalog_status.setText("Using cached data where needed: " + " | ".join(refresh.errors))
        else:
            self.catalog_status.setText(f"{len(items)} Slices available")
        self.library_changed.emit()

    def refresh_sources(self) -> None:
        self.sources.blockSignals(True)
        self.sources.clear()
        for source in self.backend.context.sources.load():
            access = "Private" if source.credential else "Public"
            if source.public_key:
                access += ", signed"
            row = QTreeWidgetItem([source.name, source.provider, source.repository, source.reference, access])
            row.setData(0, Qt.UserRole, source.id)
            row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
            row.setCheckState(0, Qt.Checked if source.enabled else Qt.Unchecked)
            self.sources.addTopLevelItem(row)
        self.sources.blockSignals(False)

    def install_selected(self) -> None:
        selected = self.available.currentItem()
        if selected is None or selected.isDisabled():
            return
        item = self.available_items[str(selected.data(0, Qt.UserRole))]
        source = next(source for source in self.backend.context.sources.load() if source.id == item.source_id)
        if source.credential and not self._ensure_private_sources_unlocked():
            return
        self.catalog_status.setText(f"Installing {item.name}…")
        task = BackgroundTask(lambda: self.backend.install_catalog_slice(item))
        task.signals.completed.connect(lambda _: self.installation_completed(item))
        task.signals.failed.connect(lambda message: QMessageBox.critical(self, "Installation failed", message))
        task.signals.finished.connect(lambda: self.active_tasks.remove(task) if task in self.active_tasks else None)
        self.active_tasks.append(task)
        self.thread_pool.start(task)

    def installation_completed(self, item: CatalogSlice) -> None:
        self.catalog_status.setText(f"Installed {item.name} {item.version}")
        self.refresh_installed()
        self.refresh_available()
        self.library_changed.emit()

    def uninstall_selected(self) -> None:
        selected = self.installed.currentItem()
        if selected is None:
            return
        manifest = selected.data(0, Qt.UserRole)
        try:
            self.backend.uninstall_managed_slice(manifest)
        except ValueError as error:
            QMessageBox.information(self, "Bundled Slice", str(error))
            return
        self.refresh_installed()
        self.library_changed.emit()

    def rollback_selected(self) -> None:
        selected = self.installed.currentItem()
        if selected is None:
            return
        manifest = selected.data(0, Qt.UserRole)
        alternatives = [
            version
            for version in self.backend.context.installer.installed_versions(manifest.id)
            if version != manifest.version
        ]
        if not alternatives:
            QMessageBox.information(self, "Slice rollback", "No previous installed version is available.")
            return
        version, accepted = QInputDialog.getItem(self, "Slice rollback", "Version", alternatives, editable=False)
        if not accepted:
            return
        try:
            self.backend.rollback_slice(manifest, version)
        except ValueError as error:
            QMessageBox.warning(self, "Slice rollback", str(error))
            return
        self.refresh_installed()
        self.library_changed.emit()

    def add_source(self) -> None:
        dialog = SourceDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        source = dialog.source_definition()
        if not source.id or not source.name or not source.repository:
            QMessageBox.warning(self, "Invalid Source", "Source ID, name, and repository are required.")
            return
        if source.provider == "forgejo" and not source.base_url:
            QMessageBox.warning(self, "Invalid Source", "Forgejo Sources require a base URL.")
            return
        if (
            not source.public_key
            and QMessageBox.warning(
                self,
                "Unsigned Source",
                "This Source has no signing key. Its catalogue cannot be authenticated. Add it anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        token = dialog.token.text().strip() or None
        if token and not self._ensure_private_sources_unlocked(create=not self.backend.context.paths.vault.exists()):
            return
        try:
            self.backend.add_source(source, token)
        except Exception as error:
            QMessageBox.critical(self, "Could not add Source", str(error))
            return
        self.refresh_sources()

    def remove_source(self) -> None:
        selected = self.sources.currentItem()
        if selected is None:
            return
        source_id = str(selected.data(0, Qt.UserRole))
        source = next(source for source in self.backend.context.sources.load() if source.id == source_id)
        if source.credential and not self._ensure_private_sources_unlocked():
            return
        self.backend.remove_source(source_id)
        self.refresh_sources()

    def lock_sources(self) -> None:
        self.backend.context.vault.lock_private_sources()
        QMessageBox.information(self, "Private Sources", "Private Sources are locked.")

    def source_enabled_changed(self, item: QTreeWidgetItem) -> None:
        self.backend.set_source_enabled(str(item.data(0, Qt.UserRole)), item.checkState(0) == Qt.Checked)

    def export_profile(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Portable Profile",
            "DoPie.dopie-profile",
            "DoPie Profile (*.dopie-profile)",
        )
        if not destination:
            return
        include_slices = (
            QMessageBox.question(self, "Export Portable Profile", "Include installed Slices?") == QMessageBox.Yes
        )
        try:
            PortableProfileService(self.backend.context.paths).export_portable_profile(
                Path(destination), include_slices
            )
        except Exception as error:
            QMessageBox.critical(self, "Profile export failed", str(error))
            return
        QMessageBox.information(self, "Portable Profile", "The portable profile was exported.")

    def import_profile(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Import Portable Profile",
            "",
            "DoPie Profile (*.dopie-profile)",
        )
        if not source:
            return
        answer = QMessageBox.question(
            self,
            "Import Portable Profile",
            "Replace the current Source configuration and private Source vault?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            PortableProfileService(self.backend.context.paths).import_portable_profile(Path(source))
        except Exception as error:
            QMessageBox.critical(self, "Profile import failed", str(error))
            return
        self.backend.context.vault.lock_private_sources()
        self.refresh_sources()
        self.refresh_installed()
        self.library_changed.emit()
