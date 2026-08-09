from __future__ import annotations

from PySide6.QtWidgets import QApplication

from dopie.models import SourceDefinition
from dopie.slice_manager.frontend import SourceDialog


def test_source_dialog_generates_optional_name_and_id(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    dialog = SourceDialog()
    dialog.repository_url.setText("https://github.com/Example/Community-Slices")
    dialog.show()
    application.processEvents()
    advanced_y = dialog.advanced_button.y()

    source = dialog.source_definition()

    assert application is not None
    assert source.name == "Community-Slices"
    assert source.id == "community-slices"
    assert source.provider == "github"
    assert not dialog.advanced.isVisible()
    assert dialog.index.parent() is dialog.advanced
    dialog.advanced_button.setChecked(True)
    application.processEvents()
    assert not dialog.advanced.isHidden()
    assert dialog.advanced_button.y() == advanced_y
    dialog.close()


def test_forgejo_is_derived_from_repository_url(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    dialog = SourceDialog()
    dialog.repository_url.setText("https://code.example.test/team/slices.git")

    source = dialog.source_definition()

    assert application is not None
    assert source.provider == "forgejo"
    assert source.base_url == "https://code.example.test"
    assert source.repository == "team/slices"
    dialog.close()


def test_source_dialog_edits_source_without_discarding_private_access(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    source = SourceDefinition(
        "private",
        "Private",
        "https://github.com/owner/private",
        credential="source:private",
    )
    dialog = SourceDialog(source=source)
    dialog.name.setText("Renamed")

    updated = dialog.source_definition()

    assert application is not None
    assert updated.name == "Renamed"
    assert updated.credential == "source:private"
    dialog.remove_token.setChecked(True)
    assert dialog.source_definition().credential is None
    dialog.close()
