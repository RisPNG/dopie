from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QPlainTextEdit, QPushButton

from dopie.models import SliceManifest
from dopie.workspace.backend import EnvironmentPlan
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


@pytest.fixture
def files_slice(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="file-selection-slice",
        name="File Selection Slice",
        version="1.0.0",
        description="Select files",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(
            {
                "id": "pdf_files",
                "label": "PDF files",
                "type": "files",
                "required": True,
                "filter": "PDF files (*.pdf)",
                "placeholder": "Select PDF files or paste their paths, one per line",
            },
            {"id": "other_files", "type": "files", "filter": "All files (*)"},
            {"id": "workbook", "type": "file", "filter": "Excel workbooks (*.xlsx)"},
            {"id": "folder", "type": "directory"},
            {"id": "recursive", "type": "boolean", "required": True},
            {"id": "limit", "type": "integer", "required": True},
            {"id": "mode", "type": "choice", "choices": ["Automatic", "Text only"]},
        ),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")
    yield widget
    widget.close()
    assert application is not None


def test_standard_slice_selects_multiple_files_with_each_field_filter(monkeypatch, files_slice):
    selected = ["/tmp/Supplier A.pdf", "/tmp/Supplier B.pdf"]
    dialogs = []

    def select_files(parent, *, filter):
        dialogs.append((parent, filter))
        return selected, filter

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", select_files)

    pdf_files = files_slice.fields["pdf_files"]
    assert isinstance(pdf_files, QPlainTextEdit)
    assert pdf_files.placeholderText() == "Select PDF files or paste their paths, one per line"
    pdf_files.parentWidget().findChild(QPushButton).click()
    files_slice.fields["other_files"].parentWidget().findChild(QPushButton).click()

    assert pdf_files.toPlainText().splitlines() == selected
    assert files_slice.fields["other_files"].toPlainText().splitlines() == selected
    assert dialogs == [(files_slice, "PDF files (*.pdf)"), (files_slice, "All files (*)")]


def test_standard_slice_preserves_multiple_files_when_picker_is_cancelled(monkeypatch, files_slice):
    pdf_files = files_slice.fields["pdf_files"]
    pdf_files.setPlainText("/tmp/Selected invoice.pdf")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([], ""))

    pdf_files.parentWidget().findChild(QPushButton).click()

    assert pdf_files.toPlainText() == "/tmp/Selected invoice.pdf"


def test_standard_slice_serializes_files_and_preserves_existing_input_values(monkeypatch, tmp_path, files_slice):
    files_slice.fields["pdf_files"].setPlainText("  /tmp/Supplier A.pdf  \n\n /tmp/Supplier B.pdf\n ")
    files_slice.fields["workbook"].setText("/tmp/report.xlsx")
    files_slice.fields["folder"].setText("/tmp/invoices")
    monkeypatch.setattr(
        files_slice.environment_manager,
        "prepare_slice_environment",
        lambda manifest: EnvironmentPlan(tmp_path / "python", ()),
    )
    monkeypatch.setattr(files_slice, "start_next_process", lambda: None)

    files_slice.start_execution()

    assert json.loads(json.dumps(files_slice.inputs)) == {
        "pdf_files": ["/tmp/Supplier A.pdf", "/tmp/Supplier B.pdf"],
        "other_files": [],
        "workbook": "/tmp/report.xlsx",
        "folder": "/tmp/invoices",
        "recursive": False,
        "limit": 0,
        "mode": "Automatic",
    }
    assert files_slice.phase == "preparing"


@pytest.mark.parametrize("paths", ["", " \n\n "])
def test_standard_slice_requires_at_least_one_file(paths, files_slice):
    files_slice.fields["pdf_files"].setPlainText(paths)

    files_slice.start_execution()

    assert files_slice.status.text() == "PDF files is required."
    assert files_slice.phase == "idle"


def test_standard_slice_keeps_single_file_and_directory_pickers(monkeypatch, files_slice):
    dialogs = []

    def select_file(parent, *, filter):
        dialogs.append((parent, filter))
        return "/tmp/report.xlsx", filter

    monkeypatch.setattr(QFileDialog, "getOpenFileName", select_file)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda parent: "/tmp/invoices")

    files_slice.fields["workbook"].parentWidget().findChild(QPushButton).click()
    files_slice.fields["folder"].parentWidget().findChild(QPushButton).click()

    assert files_slice.fields["workbook"].text() == "/tmp/report.xlsx"
    assert files_slice.fields["folder"].text() == "/tmp/invoices"
    assert dialogs == [(files_slice, "Excel workbooks (*.xlsx)")]


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
