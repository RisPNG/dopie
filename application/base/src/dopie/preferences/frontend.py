from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dopie.components.frontend import IconCheckBox
from dopie.models import SourceDefinition
from dopie.preferences.backend import PreferencesBackend


class PreferencesDialog(QDialog):
    def __init__(self, backend: PreferencesBackend, parent: QWidget | None = None):
        super().__init__(parent)
        self.backend = backend
        self.setWindowTitle("Preferences")
        self.resize(560, 390)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        general = QWidget()
        updates = QWidget()
        tabs.addTab(general, "General")
        tabs.addTab(updates, "Updates")
        general_form = QFormLayout(general)
        self.include_available = IconCheckBox("Include available Slices in Library")
        self.theme = QComboBox()
        self.theme.addItem("Follow operating system", "system")
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        general_form.addRow(self.include_available)
        general_form.addRow("Appearance", self.theme)
        update_layout = QVBoxLayout(updates)
        update_form = QFormLayout()
        self.check_updates = IconCheckBox("Check for updates on launch")
        self.check_updates.setToolTip("Check the configured repository for a newer DoPie revision after startup.")
        self.repository_url = QLineEdit()
        self.repository_url.setToolTip("The full GitHub or Forgejo repository URL containing the DoPie source.")
        self.reference = QLineEdit("main")
        self.reference.setToolTip("The repository branch DoPie follows when checking for updates.")
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("Leave blank to keep the existing token")
        self.token.setToolTip("A GitHub or Forgejo personal access token for a private repository.")
        update_form.addRow(self.check_updates)
        update_form.addRow("Repository URL", self.repository_url)
        update_form.addRow("Branch", self.reference)
        update_form.addRow("Access token", self.token)
        update_layout.addLayout(update_form)
        update_layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.save)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        preferences = backend.load_preferences()
        self.include_available.setChecked(bool(preferences.get("include_available_in_library", False)))
        theme_index = self.theme.findData(str(preferences.get("theme", "system")))
        self.theme.setCurrentIndex(max(theme_index, 0))
        self.check_updates.setChecked(bool(preferences.get("check_updates_on_launch", True)))
        update_source = preferences.get("application_update_source", {})
        if update_source and (update_source.get("repository_url") or update_source.get("repository")):
            self.repository_url.setText(SourceDefinition.from_dict(update_source).repository_url)
        self.reference.setText(str(update_source.get("reference", "main")))

    def save(self) -> None:
        try:
            previous = self.backend.load_preferences().get("application_update_source", {})
            source = SourceDefinition(
                id="dopie-application",
                name="DoPie Application",
                repository_url=self.repository_url.text().strip(),
                reference=self.reference.text().strip() or "main",
                index="index.json",
                credential=str(previous["credential"]) if previous.get("credential") else None,
            )
            self.backend.configure_application_updates(
                source,
                self.token.text().strip() or None,
                self.include_available.isChecked(),
                self.check_updates.isChecked(),
            )
            preferences = self.backend.load_preferences()
            preferences["theme"] = self.theme.currentData()
            self.backend.save_preferences(preferences)
        except Exception as error:
            QMessageBox.warning(self, "Preferences", str(error))
            return
        self.accept()
