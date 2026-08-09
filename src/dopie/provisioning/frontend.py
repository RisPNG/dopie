from __future__ import annotations

from cryptography.exceptions import InvalidTag
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from dopie.provisioning.backend import ProvisioningBackend


def provision_portable_copy(backend: ProvisioningBackend, parent: QWidget | None = None) -> bool:
    try:
        pending = backend.pending_provisioning()
    except Exception as error:
        QMessageBox.warning(parent, "Provisioning profile", f"The provisioned profile is invalid: {error}")
        return False
    if pending is None:
        return True
    if not pending.requires_password:
        try:
            backend.apply_provisioning(pending)
        except Exception as error:
            QMessageBox.warning(parent, "Provisioning failed", str(error))
            return False
        return True
    while True:
        password, accepted = QInputDialog.getText(
            parent,
            "Authorize Private Sources",
            "Transfer password",
            QLineEdit.Password,
        )
        if not accepted or not password:
            return False
        try:
            backend.apply_provisioning(pending, password)
        except InvalidTag:
            QMessageBox.warning(parent, "Source authorization failed", "The transfer password is incorrect.")
            continue
        except Exception as error:
            QMessageBox.warning(parent, "Provisioning failed", str(error))
            return False
        return True
