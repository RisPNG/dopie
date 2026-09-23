from __future__ import annotations

import zipfile

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from dopie.context import ApplicationContext, VaultSession
from dopie.models import SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.provisioning.backend import ProvisioningBackend
from dopie.provisioning.frontend import provision_portable_copy
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slice_manager.frontend import SliceManagerPage
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import SettingsStore, SourceStore


@pytest.mark.parametrize(
    "responses, exported, warning",
    [
        ([("", True)], True, False),
        ([("", False)], False, False),
        ([("password", True), ("password", True)], True, False),
        ([("password", True), ("different", True)], False, True),
        ([("password", True), ("", False)], False, False),
    ],
)
def test_private_copy_export_and_first_launch(tmp_path, monkeypatch, responses, exported, warning):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path / "source"))
    paths = resolve_app_paths()
    context = ApplicationContext(
        paths,
        SettingsStore(paths.settings),
        SourceStore(paths.sources),
        VaultSession(VaultStore(paths.vault, paths.vault_key)),
        SliceDiscovery(paths.bundled_slices, paths.installed_slices),
        SliceInstaller(paths.installed_slices),
    )
    source = SourceDefinition(
        "private", "Private", "https://github.com/owner/private", credential="source:private"
    )
    backend = SliceManagerBackend(context)
    backend.add_source(source, "private-token")
    application = QApplication.instance() or QApplication([])
    page = SliceManagerPage(backend)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "copy.zip"), ""))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: ("Linux", True))
    answers = iter(responses)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: next(answers))
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append("success"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append("warning"))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append("error"))
    try:
        page.export_portable_copy()
        assert list(answers) == []
        copies = list(tmp_path.glob("copy-*.zip"))
        assert bool(copies) == exported
        assert messages == (["success"] if exported else ["warning"] if warning else [])
        assert not list(paths.data.glob("dopie-export-*"))
        if exported:
            with zipfile.ZipFile(copies[0]) as archive:
                archive.extractall(tmp_path / "received")
            monkeypatch.setenv("DOPIE_ROOT", str(tmp_path / "received" / "DoPie"))
            received = resolve_app_paths()
            provisioning = ProvisioningBackend(received)
            password = responses[0][0]
            assert provisioning.pending_provisioning().requires_password == bool(password)
            prompts = iter([(password, True)] if password else [])
            monkeypatch.setattr(QInputDialog, "getText", lambda *args: next(prompts))

            assert provision_portable_copy(provisioning)
            assert list(prompts) == []
            assert provisioning.pending_provisioning() is None
            assert SourceStore(received.sources).load() == [source]
            assert VaultStore(received.vault, received.vault_key).unlock() == {
                "credentials": {"source:private": "private-token"}
            }
            assert received.vault_key.read_bytes() != paths.vault_key.read_bytes()
    finally:
        page.close()
    assert application is not None
