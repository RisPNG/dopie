from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QListWidget, QPushButton

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


def test_standard_slice_collects_browsed_files_as_a_list(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="files-slice",
        name="Files Slice",
        version="1.0.0",
        description="Files Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=({"id": "documents", "label": "Documents", "type": "files", "required": True},),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")
    monkeypatch.setattr(widget, "start_next_process", lambda: None)
    selections = iter(
        [
            (["/august/summary.xlsx", "/august/notes.pdf"], ""),
            ([], ""),
            (["/september/summary.xlsx", "/august/notes.pdf"], ""),
        ]
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *arguments: next(selections))

    documents = widget.fields["documents"]
    assert isinstance(documents, QListWidget)
    browse = next(button for button in documents.parentWidget().findChildren(QPushButton) if button.text() == "Browse")
    for _ in range(3):
        browse.click()
    widget.start_execution()

    assert widget.inputs["documents"] == ["/august/summary.xlsx", "/august/notes.pdf", "/september/summary.xlsx"]
    assert widget.phase == "preparing"
    widget.close()
    assert application is not None


def test_standard_slice_removes_only_selected_files(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="files-slice",
        name="Files Slice",
        version="1.0.0",
        description="Files Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=({"id": "documents", "label": "Documents", "type": "files"},),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")
    documents = widget.fields["documents"]
    documents.addItems(["/first.pdf", "/second.pdf", "/third.pdf"])
    remove = next(
        button for button in documents.parentWidget().findChildren(QPushButton) if button.text() == "Remove selected"
    )

    remove.click()
    assert documents.count() == 3

    documents.item(0).setSelected(True)
    documents.item(2).setSelected(True)
    remove.click()

    assert [documents.item(index).text() for index in range(documents.count())] == ["/second.pdf"]
    widget.close()
    assert application is not None


def test_standard_slice_requires_at_least_one_file_and_passes_unpicked_files_as_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="files-slice",
        name="Files Slice",
        version="1.0.0",
        description="Files Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(
            {"id": "attachments", "label": "Attachments", "type": "files"},
            {"id": "documents", "label": "Documents", "type": "files", "required": True},
        ),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")
    monkeypatch.setattr(widget, "start_next_process", lambda: None)

    widget.start_execution()

    assert widget.status.text() == "Documents is required."
    assert widget.phase == "idle"

    widget.fields["documents"].addItem("/report.xlsx")
    widget.start_execution()

    assert widget.inputs["attachments"] == []
    assert widget.inputs["documents"] == ["/report.xlsx"]
    assert widget.phase == "preparing"
    widget.close()
    assert application is not None


def test_standard_slice_accepts_zero_and_unchecked_required_values(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="values-slice",
        name="Values Slice",
        version="1.0.0",
        description="Values Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(
            {"id": "count", "label": "Count", "type": "integer", "required": True},
            {"id": "overwrite", "label": "Overwrite", "type": "boolean", "required": True},
        ),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")
    monkeypatch.setattr(widget, "start_next_process", lambda: None)

    widget.start_execution()

    assert widget.inputs["count"] == 0
    assert widget.inputs["overwrite"] is False
    assert widget.phase == "preparing"
    widget.close()
    assert application is not None


def test_standard_slice_file_and_directory_browse_fill_their_line_edits(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="paths-slice",
        name="Paths Slice",
        version="1.0.0",
        description="Paths Slice",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(
            {"id": "workbook", "label": "Workbook", "type": "file"},
            {"id": "output", "label": "Output", "type": "directory"},
        ),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=Path(tmp_path),
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", tmp_path / "worker.py")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *arguments: ("/august/summary.xlsx", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *arguments: "/august")

    for field_id in ("workbook", "output"):
        field = widget.fields[field_id]
        assert isinstance(field, QLineEdit)
        field.parentWidget().findChild(QPushButton).click()

    assert widget.fields["workbook"].text() == "/august/summary.xlsx"
    assert widget.fields["output"].text() == "/august"
    widget.close()
    assert application is not None
