from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
        self.include_available = QCheckBox("Include available Slices in Library")
        self.theme = QComboBox()
        self.theme.addItem("Follow operating system", "system")
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.vault_timeout = QSpinBox()
        self.vault_timeout.setRange(0, 1440)
        self.vault_timeout.setSuffix(" minutes")
        self.vault_timeout.setSpecialValueText("Never")
        general_form.addRow(self.include_available)
        general_form.addRow("Appearance", self.theme)
        general_form.addRow("Lock private Sources after", self.vault_timeout)
        update_form = QFormLayout(updates)
        self.check_updates = QCheckBox("Check for updates on launch")
        self.provider = QComboBox()
        self.provider.addItems(["GitHub", "Forgejo"])
        self.base_url = QLineEdit()
        self.repository = QLineEdit()
        self.repository.setPlaceholderText("owner/repository")
        self.reference = QLineEdit("main")
        self.public_key = QLineEdit()
        self.public_key.setPlaceholderText("Optional base64 Ed25519 public key")
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.vault_password = QLineEdit()
        self.vault_password.setEchoMode(QLineEdit.Password)
        self.confirm_vault_password = QLineEdit()
        self.confirm_vault_password.setEchoMode(QLineEdit.Password)
        update_form.addRow(self.check_updates)
        update_form.addRow("Provider", self.provider)
        update_form.addRow("Forgejo base URL", self.base_url)
        update_form.addRow("Repository", self.repository)
        update_form.addRow("Branch", self.reference)
        update_form.addRow("Signing key", self.public_key)
        update_form.addRow("New access token", self.token)
        update_form.addRow("Source vault password", self.vault_password)
        update_form.addRow("Confirm new vault password", self.confirm_vault_password)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.save)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        preferences = backend.load_preferences()
        self.include_available.setChecked(bool(preferences.get("include_available_in_library", False)))
        theme_index = self.theme.findData(str(preferences.get("theme", "system")))
        self.theme.setCurrentIndex(max(theme_index, 0))
        self.vault_timeout.setValue(int(preferences.get("vault_lock_minutes", 15)))
        self.check_updates.setChecked(bool(preferences.get("check_updates_on_launch", True)))
        update_source = preferences.get("application_update_source", {})
        provider_index = self.provider.findText(str(update_source.get("provider", "github")).title())
        self.provider.setCurrentIndex(max(provider_index, 0))
        self.base_url.setText(str(update_source.get("base_url") or ""))
        self.repository.setText(str(update_source.get("repository") or ""))
        self.reference.setText(str(update_source.get("reference", "main")))
        self.public_key.setText(str(update_source.get("public_key") or ""))

    def save(self) -> None:
        if (
            self.token.text()
            and not self.backend.context.paths.vault.exists()
            and self.vault_password.text() != self.confirm_vault_password.text()
        ):
            QMessageBox.warning(self, "Preferences", "Source vault passwords do not match.")
            return
        if (
            self.repository.text().strip()
            and not self.public_key.text().strip()
            and QMessageBox.warning(
                self,
                "Unsigned updates",
                "This update Source has no signing key. Updates cannot be authenticated. Save it anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        previous = self.backend.load_preferences().get("application_update_source", {})
        source = SourceDefinition(
            id="dopie-application",
            name="DoPie Application",
            provider=self.provider.currentText().casefold(),
            base_url=self.base_url.text().strip() or None,
            repository=self.repository.text().strip(),
            reference=self.reference.text().strip(),
            index="index.json",
            credential=str(previous["credential"]) if previous.get("credential") else None,
            public_key=self.public_key.text().strip() or None,
        )
        try:
            self.backend.configure_application_updates(
                source,
                self.token.text().strip() or None,
                self.vault_password.text() or None,
                self.include_available.isChecked(),
                self.check_updates.isChecked(),
            )
            preferences = self.backend.load_preferences()
            preferences["theme"] = self.theme.currentData()
            preferences["vault_lock_minutes"] = self.vault_timeout.value()
            self.backend.save_preferences(preferences)
        except Exception as error:
            QMessageBox.warning(self, "Preferences", str(error))
            return
        self.accept()
