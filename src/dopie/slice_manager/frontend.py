from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
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
    def __init__(self, parent: QWidget | None = None, source: SourceDefinition | None = None):
        super().__init__(parent)
        self.existing = source
        self.setWindowTitle("Edit Source" if source else "Add Source")
        self.resize(560, 340)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Uses the repository name when empty")
        self.name.setToolTip("Optional display name. When empty, DoPie uses the repository name.")
        self.repository_url = QLineEdit()
        self.repository_url.setPlaceholderText("https://github.com/owner/repository")
        self.repository_url.setToolTip("The full GitHub or Forgejo repository URL containing the Slice catalogue.")
        self.reference = QLineEdit("main")
        self.reference.setToolTip("The repository branch containing the catalogue and Slice packages.")
        self.index = QLineEdit("index.json")
        self.index.setToolTip(
            "The catalogue file DoPie reads to discover available Slices. "
            "Keep index.json unless the Source stores it elsewhere."
        )
        form.addRow("Name", self.name)
        form.addRow("Repository URL", self.repository_url)
        form.addRow("Branch", self.reference)
        self.advanced_button = QToolButton()
        self.advanced_button.setText("Advanced")
        self.advanced_button.setCheckable(True)
        self.advanced_button.setArrowType(Qt.RightArrow)
        self.advanced_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced = QWidget()
        self.advanced.setVisible(False)
        advanced_form = QFormLayout(self.advanced)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        self.source_id = QLineEdit()
        self.source_id.setPlaceholderText("Generated from the repository name")
        self.source_id.setToolTip("Optional stable local identifier using lowercase letters, numbers, and hyphens.")
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText(
            "Leave blank to keep the saved token"
            if source and source.credential
            else "Optional for private repositories"
        )
        self.token.setToolTip("A repository-scoped personal access token, encrypted inside this DoPie folder.")
        self.remove_token = QCheckBox("Remove saved access token")
        self.remove_token.setVisible(bool(source and source.credential))
        self.remove_token.toggled.connect(self.token.setDisabled)
        advanced_form.addRow("Source ID", self.source_id)
        advanced_form.addRow("Index", self.index)
        advanced_form.addRow("Access token", self.token)
        advanced_form.addRow(self.remove_token)
        self.advanced_button.toggled.connect(self.advanced.setVisible)
        self.advanced_button.toggled.connect(
            lambda expanded: self.advanced_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addLayout(form)
        layout.addWidget(self.advanced_button, 0, Qt.AlignLeft)
        layout.addWidget(self.advanced)
        layout.addStretch()
        layout.addWidget(buttons)
        if source:
            self.name.setText(source.name)
            self.repository_url.setText(source.repository_url)
            self.reference.setText(source.reference)
            self.source_id.setText(source.id)
            self.index.setText(source.index)

    def source_definition(self) -> SourceDefinition:
        token = self.token.text().strip()
        repository_url = self.repository_url.text().strip()
        repository_name = urlparse(repository_url).path.strip("/").rsplit("/", 1)[-1].removesuffix(".git")
        source_id = self.source_id.text().strip() or re.sub(
            r"[^a-z0-9]+", "-", (repository_name or "source").casefold()
        ).strip("-")
        if self.remove_token.isChecked():
            credential = None
        elif self.existing and self.existing.credential:
            credential = self.existing.credential
        else:
            credential = f"source:{source_id}" if token else None
        return SourceDefinition(
            id=source_id,
            name=self.name.text().strip() or repository_name or "Source",
            repository_url=repository_url,
            reference=self.reference.text().strip() or "main",
            index=self.index.text().strip() or "index.json",
            credential=credential,
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
        self.installed.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.installed.header().setStretchLastSection(True)
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
        self.available.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.available.header().setStretchLastSection(True)
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
        edit = QPushButton("Edit selected")
        edit.clicked.connect(self.edit_source)
        export_copy = QPushButton("Export Portable Copy")
        export_copy.clicked.connect(self.export_portable_copy)
        import_profile = QPushButton("Import Profile")
        import_profile.clicked.connect(self.import_profile)
        toolbar.addWidget(add)
        toolbar.addWidget(edit)
        toolbar.addWidget(remove)
        toolbar.addWidget(export_copy)
        toolbar.addWidget(import_profile)
        toolbar.addStretch()
        self.sources = QTreeWidget()
        self.sources.setHeaderLabels(["Source", "Repository URL", "Branch", "Access"])
        self.sources.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sources.header().setStretchLastSection(True)
        self.sources.itemChanged.connect(self.source_enabled_changed)
        layout.addLayout(toolbar)
        layout.addWidget(self.sources)

    def refresh_installed(self) -> None:
        self.installed.clear()
        for manifest in self.backend.installed_slices():
            origin = "Installed" if manifest.origin == "installed" else "Bundled"
            row = QTreeWidgetItem([manifest.name, manifest.version, manifest.category, origin])
            row.setData(0, Qt.UserRole, manifest)
            self.installed.addTopLevelItem(row)

    def refresh_available(self) -> None:
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
            row = QTreeWidgetItem([source.name, source.repository_url, source.reference, access])
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
        try:
            source = dialog.source_definition()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Source", str(error))
            return
        token = dialog.token.text().strip() or None
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
        self.backend.remove_source(source_id)
        self.refresh_sources()

    def edit_source(self) -> None:
        selected = self.sources.currentItem()
        if selected is None:
            return
        source_id = str(selected.data(0, Qt.UserRole))
        source = next(source for source in self.backend.context.sources.load() if source.id == source_id)
        dialog = SourceDialog(self, source)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.backend.update_source(source_id, dialog.source_definition(), dialog.token.text().strip() or None)
        except Exception as error:
            QMessageBox.critical(self, "Could not update Source", str(error))
            return
        self.refresh_sources()

    def source_enabled_changed(self, item: QTreeWidgetItem) -> None:
        self.backend.set_source_enabled(str(item.data(0, Qt.UserRole)), item.checkState(0) == Qt.Checked)

    def export_portable_copy(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Portable Copy",
            "DoPie-portable.zip",
            "ZIP archive (*.zip)",
        )
        if not destination:
            return
        include_slices = (
            QMessageBox.question(self, "Export Portable Copy", "Include installed Slices?") == QMessageBox.Yes
        )
        include_runtime = (
            QMessageBox.question(
                self,
                "Export Portable Copy",
                "Include the downloaded runtime for this operating system?",
            )
            == QMessageBox.Yes
        )
        password = None
        if self.backend.context.paths.vault.exists():
            password, accepted = QInputDialog.getText(
                self,
                "Protect Private Sources",
                "Transfer password",
                QLineEdit.Password,
            )
            if not accepted or not password:
                return
            confirmation, confirmed = QInputDialog.getText(
                self,
                "Protect Private Sources",
                "Confirm transfer password",
                QLineEdit.Password,
            )
            if not confirmed or password != confirmation:
                QMessageBox.warning(self, "Protect Private Sources", "Transfer passwords do not match.")
                return
        try:
            PortableProfileService(self.backend.context.paths).export_portable_copy(
                Path(destination), include_slices, include_runtime, password
            )
        except Exception as error:
            QMessageBox.critical(self, "Portable copy export failed", str(error))
            return
        QMessageBox.information(self, "Portable Copy", "The transferable DoPie ZIP was exported.")

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
        profile = PortableProfileService(self.backend.context.paths)
        password = None
        if profile.profile_requires_password(Path(source)):
            password, accepted = QInputDialog.getText(
                self,
                "Authorize Private Sources",
                "Transfer password",
                QLineEdit.Password,
            )
            if not accepted or not password:
                return
        try:
            profile.import_portable_profile(Path(source), password)
        except Exception as error:
            QMessageBox.critical(self, "Profile import failed", str(error))
            return
        self.backend.context.vault.secrets = None
        self.refresh_sources()
        self.refresh_installed()
        self.library_changed.emit()
