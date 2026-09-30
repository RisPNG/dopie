from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from dopie.context import ApplicationContext
from dopie.models import SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.provisioning.backend import ProvisioningBackend
from dopie.provisioning.frontend import provision_portable_copy
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slice_manager.frontend import SliceManagerPage
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.sources.profile import PortableProfileService
from dopie.storage import DEFAULT_SHARED_SETTINGS, SettingsStore, SourceStore


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
        SettingsStore(paths.shared_settings, DEFAULT_SHARED_SETTINGS),
        SourceStore(paths.sources),
        VaultStore(paths.vault, paths.vault_key),
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


def test_exporting_an_older_application_keeps_the_bootstrap_independent(tmp_path, monkeypatch):
    root = tmp_path / "source"
    older = root / "application" / "versions" / "1.1.6-previous"
    older.joinpath("src", "dopie").mkdir(parents=True)
    older.joinpath("src", "dopie", "__init__.py").write_text('__version__ = "1.1.6"\n', encoding="utf-8")
    older.joinpath("requirements.lock").write_text("", encoding="utf-8")
    older.joinpath("pyproject.toml").write_text('[project]\nname = "dopie"\nversion = "1.1.6"\n', encoding="utf-8")
    shutil.copytree(Path(__file__).parents[1] / "bootstrap", root / "bootstrap")
    monkeypatch.setenv("DOPIE_ROOT", str(root))
    monkeypatch.setenv("DOPIE_ACTIVE_ROOT", str(older))
    paths = resolve_app_paths()
    exported = tmp_path / "copy.zip"

    PortableProfileService(paths).export_portable_copy(exported, "linux")

    with zipfile.ZipFile(exported) as archive:
        assert "DoPie/application/base/src/dopie/shared_folder.py" not in archive.namelist()
        archive.extractall(tmp_path / "received")
    bootstrap = tmp_path / "received" / "DoPie" / "bootstrap" / "bootstrap.py"
    loaded = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "import runpy, sys; from pathlib import Path; module = runpy.run_path(sys.argv[1]); "
            "application, activated = module['activate_prepared_update'](Path(sys.argv[1]).parent.parent); "
            "print(application.name, activated)",
            str(bootstrap),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "base False"
