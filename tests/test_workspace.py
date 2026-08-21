from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QLineEdit

from dopie.models import SliceManifest
from dopie.workspace.frontend import StandardSliceWidget


def test_standard_slice_masks_and_requires_password_input(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="secure-slice",
        name="Secure Slice",
        version="1.0.0",
        description="Secure Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(
            {
                "id": "password",
                "label": "Password",
                "type": "password",
                "required": True,
                "placeholder": "Enter password",
            },
        ),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")

    password = widget.fields["password"]
    assert isinstance(password, QLineEdit)
    assert password.echoMode() == QLineEdit.Password
    assert password.placeholderText() == "Enter password"

    widget.start_execution()

    assert widget.status.text() == "Password is required."
    assert widget.phase == "idle"
    widget.close()
    assert application is not None


def test_standard_slice_prefills_masked_password_default(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="default-password-slice",
        name="Default Password Slice",
        version="1.0.0",
        description="Default Password Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(
            {
                "id": "password",
                "label": "Password",
                "type": "password",
                "required": True,
                "default": "placeholder-password",
            },
        ),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")

    password = widget.fields["password"]
    assert isinstance(password, QLineEdit)
    assert password.echoMode() == QLineEdit.Password
    assert password.text() == "placeholder-password"

    widget.close()
    assert application is not None
