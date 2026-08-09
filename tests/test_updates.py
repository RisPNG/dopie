from __future__ import annotations

import json
import zipfile
from io import BytesIO
from types import SimpleNamespace

from dopie.models import SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient
from dopie.updates.service import ApplicationUpdateService


def test_first_update_check_records_current_revision_without_reporting_an_update(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    project.joinpath("pyproject.toml").write_text(
        '[project]\nname = "dopie"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    state = tmp_path / "application" / "current.json"
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "current-revision")

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(source)

    assert revision is None
    assert json.loads(state.read_text(encoding="utf-8")) == {
        "version": "0.1.0",
        "revision": "current-revision",
        "path": str(project),
    }


def test_update_check_reports_a_revision_changed_after_the_baseline(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    project.joinpath("pyproject.toml").write_text(
        '[project]\nname = "dopie"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    state = tmp_path / "application" / "current.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps({"version": "0.1.0", "revision": "current-revision", "path": str(project)}),
        encoding="utf-8",
    )
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "new-revision")

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(source)

    assert revision == "new-revision"
    assert json.loads(state.read_text(encoding="utf-8"))["revision"] == "current-revision"


def test_first_update_check_compares_a_git_checkout_before_recording_its_baseline(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    project.joinpath(".git").mkdir()
    project.joinpath("pyproject.toml").write_text(
        '[project]\nname = "dopie"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    state = tmp_path / "application" / "current.json"
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "new-revision")
    monkeypatch.setattr("dopie.updates.service.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        "dopie.updates.service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="checkout-revision\n"),
    )

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(source)

    assert revision == "new-revision"
    assert json.loads(state.read_text(encoding="utf-8"))["revision"] == "checkout-revision"


def test_update_check_refreshes_stale_state_from_an_advanced_git_checkout(tmp_path, monkeypatch):
    checkout = tmp_path / "project"
    project = checkout / "application" / "base"
    project.mkdir(parents=True)
    checkout.joinpath(".git").mkdir()
    project.joinpath("pyproject.toml").write_text(
        '[project]\nname = "dopie"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    state = tmp_path / "application" / "current.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps({"version": "0.1.0", "revision": "stale-revision", "path": str(project)}),
        encoding="utf-8",
    )
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "checkout-revision")
    monkeypatch.setattr("dopie.updates.service.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        "dopie.updates.service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="checkout-revision\n"),
    )

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(source)

    assert revision is None
    assert json.loads(state.read_text(encoding="utf-8"))["revision"] == "checkout-revision"


def test_prepares_application_update_without_touching_active_source(tmp_path, monkeypatch):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(
            "dopie-next/application/base/pyproject.toml",
            '[project]\nname = "dopie"\nversion = "0.2.0"\n',
        )
        package.writestr("dopie-next/application/base/src/dopie/__init__.py", '__version__ = "0.2.0"\n')
        package.writestr("dopie-next/application/base/src/dopie/application.py", "def main(): return 0\n")
        package.writestr("dopie-next/application/base/requirements.lock", "")
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "download_repository_archive",
        lambda self, revision: archive.getvalue(),
    )
    updates = tmp_path / "updates"
    updates.mkdir()
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")

    state = ApplicationUpdateService(
        updates,
        tmp_path / "application" / "current.json",
        tmp_path,
    ).prepare_update(source, "abcdef1234")

    assert state["version"] == "0.2.0"
    assert (updates / "prepared" / "src" / "dopie" / "__init__.py").exists()
    assert json.loads((updates / "pending.json").read_text(encoding="utf-8"))["revision"] == "abcdef1234"
