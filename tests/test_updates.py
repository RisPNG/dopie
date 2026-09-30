from __future__ import annotations

import importlib.util
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from dopie.models import SourceDefinition
from dopie.shared_folder import shared_folder_transaction
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
    assert (updates / "prepared-abcdef12" / "src" / "dopie" / "__init__.py").exists()
    assert json.loads((updates / "pending.json").read_text(encoding="utf-8"))["revision"] == "abcdef1234"
    assert not list(updates.glob("*.tmp"))
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "download_repository_archive",
        lambda self, revision: pytest.fail("A prepared revision is downloaded again"),
    )
    assert ApplicationUpdateService(
        updates,
        tmp_path / "application" / "current.json",
        tmp_path,
    ).prepare_update(source, "abcdef1234") == state


def test_managed_application_keeps_its_revision_inside_a_newer_checkout(tmp_path, monkeypatch):
    checkout = tmp_path / "project"
    project = checkout / "application" / "versions" / "1.1.3-old-revision"
    project.mkdir(parents=True)
    checkout.joinpath(".git").mkdir()
    state = checkout / "application" / "current.json"
    installed = {
        "version": "1.1.3",
        "revision": "old-revision",
        "path": str(project),
        "previous": {"version": "1.1.2", "revision": "previous-revision", "path": "previous"},
    }
    state.write_text(json.dumps(installed), encoding="utf-8")
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "checkout-revision")
    monkeypatch.setattr("dopie.updates.service.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        "dopie.updates.service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="checkout-revision\n"),
    )

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(source)

    assert revision == "checkout-revision"
    assert json.loads(state.read_text(encoding="utf-8")) == installed


def test_preparing_a_revision_another_user_already_prepared_keeps_theirs(tmp_path, monkeypatch):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("dopie-next/application/base/pyproject.toml", '[project]\nname = "dopie"\nversion = "0.2.0"\n')
        package.writestr("dopie-next/application/base/src/dopie/application.py", "def main(): return 0\n")
        package.writestr("dopie-next/application/base/requirements.lock", "")
    monkeypatch.setattr(
        RemoteRepositoryClient, "download_repository_archive", lambda self, revision: archive.getvalue()
    )
    updates = tmp_path / "updates"
    theirs = updates / "prepared-abcdef12"
    theirs.mkdir(parents=True)
    theirs.joinpath("theirs").write_text("", encoding="utf-8")
    updates.joinpath("pending.json").write_text(
        json.dumps({"version": "0.1.9", "revision": "0123456789", "path": str(updates / "prepared-01234567")}),
        encoding="utf-8",
    )

    state = ApplicationUpdateService(updates, tmp_path / "application" / "current.json", tmp_path).prepare_update(
        SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie"), "abcdef1234"
    )

    assert state == {"version": "0.2.0", "revision": "abcdef1234", "path": str(theirs)}
    assert theirs.joinpath("theirs").exists()
    assert json.loads(updates.joinpath("pending.json").read_text(encoding="utf-8")) == state


@pytest.mark.parametrize(
    "recorded",
    [
        r"Z:\Else\DoPie\application\versions\1.2.0-new-revi",
        "/mnt/else/DoPie/application/versions/1.2.0-new-revi",
    ],
)
def test_an_old_checkout_session_preserves_an_activation_during_its_update_check(tmp_path, monkeypatch, recorded):
    project = tmp_path / "application" / "base"
    project.mkdir(parents=True)
    tmp_path.joinpath(".git").mkdir()
    project.joinpath("pyproject.toml").write_text('[project]\nversion = "1.1.6"\n', encoding="utf-8")
    state = project.parent / "current.json"
    state.write_text(
        json.dumps({"version": "1.1.6", "revision": "old-revision", "path": str(project)}), encoding="utf-8"
    )
    activated = {
        "version": "1.2.0",
        "revision": "new-revision",
        "path": recorded,
        "previous": {"version": "1.1.6", "revision": "old-revision", "path": str(project)},
    }

    def resolve_revision(self):
        with shared_folder_transaction(state.parent / ".updates.lock"):
            state.write_text(json.dumps(activated), encoding="utf-8")
        return "new-revision"

    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", resolve_revision)
    monkeypatch.setattr("dopie.updates.service.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        "dopie.updates.service.subprocess.run", lambda *args, **kwargs: pytest.fail("An old session reconciled Git")
    )

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(
        SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    )

    assert revision is None
    assert json.loads(state.read_text(encoding="utf-8")) == activated


@pytest.mark.parametrize("recorded", [r"Z:\Else\DoPie\application\base", "/mnt/else/DoPie/application/base"])
def test_a_selected_checkout_reconciles_its_revision_through_another_mount(tmp_path, monkeypatch, recorded):
    project = tmp_path / "application" / "base"
    project.mkdir(parents=True)
    tmp_path.joinpath(".git").mkdir()
    project.joinpath("pyproject.toml").write_text('[project]\nversion = "1.2.0"\n', encoding="utf-8")
    state = project.parent / "current.json"
    state.write_text(
        json.dumps({"version": "1.1.6", "revision": "stale-revision", "path": recorded}), encoding="utf-8"
    )
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "checkout-revision")
    monkeypatch.setattr("dopie.updates.service.shutil.which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        "dopie.updates.service.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout="checkout-revision\n")
    )

    revision = ApplicationUpdateService(tmp_path / "updates", state, project).check_for_update(
        SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")
    )

    assert revision is None
    assert json.loads(state.read_text(encoding="utf-8")) == {
        "version": "1.2.0", "revision": "checkout-revision", "path": str(project)
    }


def test_an_update_activated_during_download_is_not_prepared_again(tmp_path, monkeypatch):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("dopie/application/base/pyproject.toml", '[project]\nversion = "1.2.0"\n')
        package.writestr("dopie/application/base/src/dopie/application.py", "def main(): return 0\n")
        package.writestr("dopie/application/base/requirements.lock", "")
    updates = tmp_path / "data" / "updates"
    updates.mkdir(parents=True)
    state = tmp_path / "application" / "current.json"
    activated = {"version": "1.2.0", "revision": "abcdef1234", "path": "application/versions/1.2.0-abcdef12"}

    def download_repository_archive(self, revision):
        with shared_folder_transaction(state.parent / ".updates.lock"):
            state.write_text(json.dumps(activated), encoding="utf-8")
        return archive.getvalue()

    monkeypatch.setattr(RemoteRepositoryClient, "download_repository_archive", download_repository_archive)
    service = ApplicationUpdateService(updates, state, tmp_path)
    source = SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie")

    assert service.prepare_update(source, "abcdef1234") == activated
    assert not updates.joinpath("pending.json").exists()
    assert not list(updates.iterdir())
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "download_repository_archive",
        lambda self, revision: pytest.fail("An active revision was downloaded again"),
    )
    assert service.prepare_update(source, "abcdef1234") == activated


def test_pending_publication_finishes_before_another_user_activates_it(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "dopie_update_publication_bootstrap", Path(__file__).parents[1] / "bootstrap" / "bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("dopie/application/base/pyproject.toml", '[project]\nversion = "1.2.0"\n')
        package.writestr("dopie/application/base/src/dopie/application.py", "def main(): return 0\n")
        package.writestr("dopie/application/base/requirements.lock", "")
    monkeypatch.setattr(
        RemoteRepositoryClient, "download_repository_archive", lambda self, revision: archive.getvalue()
    )
    updates = tmp_path / "data" / "updates"
    updates.mkdir(parents=True)
    state = tmp_path / "application" / "current.json"
    publication_started = Event()
    activation_attempted = Event()
    activation_finished = Event()
    rename = Path.rename

    def publish(self, destination):
        result = rename(self, destination)
        if Path(destination) == updates / "prepared-abcdef12":
            publication_started.set()
            assert activation_attempted.wait(5)
            assert not activation_finished.wait(0.1)
        return result

    def activate():
        assert publication_started.wait(5)
        activation_attempted.set()
        activated = bootstrap.activate_prepared_update(tmp_path)
        activation_finished.set()
        return activated

    monkeypatch.setattr(Path, "rename", publish)
    service = ApplicationUpdateService(updates, state, tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        activation = executor.submit(activate)
        preparation = executor.submit(
            service.prepare_update, SourceDefinition("dopie", "DoPie", "https://github.com/owner/dopie"), "abcdef1234"
        )
        assert preparation.result(timeout=5)["revision"] == "abcdef1234"
        assert activation.result(timeout=5) == (state.parent / "versions" / "1.2.0-abcdef12", True)

    assert activation_finished.is_set()
    assert json.loads(state.read_text(encoding="utf-8"))["revision"] == "abcdef1234"
    assert not updates.joinpath("pending.json").exists()
    assert not list(updates.iterdir())
