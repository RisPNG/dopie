from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, current_thread

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from dopie.context import ApplicationContext
from dopie.library.backend import LibraryBackend
from dopie.models import SliceManifest, SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.preferences.backend import PreferencesBackend
from dopie.preferences.frontend import PreferencesDialog
from dopie.security.vault import VaultStore
from dopie.slice_manager.backend import SliceManagerBackend
from dopie.slice_manager.frontend import SliceManagerPage
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.storage import DEFAULT_SHARED_SETTINGS, SettingsStore, SourceStore
from dopie.workspace.backend import EnvironmentPlan
from dopie.workspace.frontend import StandardSliceWidget

PRIVATE = SourceDefinition("private", "Private", "https://github.com/owner/private", credential="source:private")
OTHER = SourceDefinition("other", "Other", "https://github.com/owner/other", credential="source:other")
CUSTOM_UPDATES = SourceDefinition("dopie-application", "DoPie Application", "https://git.example.test/team/dopie")
WORKER = Path(__file__).parents[1] / "application" / "base" / "src" / "dopie" / "slices" / "worker.py"


def open_as(user, root, monkeypatch):
    monkeypatch.setenv("LOGNAME", user)
    monkeypatch.setenv("DOPIE_ROOT", str(root))
    paths = resolve_app_paths()
    return SliceManagerBackend(
        ApplicationContext(
            paths,
            SettingsStore(paths.settings),
            SettingsStore(paths.shared_settings, DEFAULT_SHARED_SETTINGS),
            SourceStore(paths.sources),
            VaultStore(paths.vault, paths.vault_key),
            SliceDiscovery(paths.bundled_slices, paths.installed_slices),
            SliceInstaller(paths.installed_slices),
        )
    )


def install_slice(installed: Path, slice_id: str) -> None:
    version = installed / slice_id / "versions" / "1.0.0"
    version.mkdir(parents=True)
    version.joinpath("slice.toml").write_text(
        f'id="{slice_id}"\nname="{slice_id}"\nversion="1.0.0"\ndescription="{slice_id}"\ninterface="standard"\n'
        'operation="backend:run"',
        encoding="utf-8",
    )
    installed.joinpath(slice_id, "current.json").write_text('{"version": "1.0.0"}', encoding="utf-8")


def test_each_user_has_their_own_preferences_and_installed_slices(tmp_path, monkeypatch):
    alice = open_as("alice", tmp_path, monkeypatch)
    install_slice(alice.context.paths.installed_slices, "alice-tool")
    LibraryBackend(alice.context).set_slice_favorite("alice-tool", True)
    bob = open_as("bob", tmp_path, monkeypatch)
    install_slice(bob.context.paths.installed_slices, "bob-tool")

    assert alice.context.paths.installed_slices == tmp_path / "data" / "users" / "alice" / "slices"
    assert alice.context.paths.settings == tmp_path / "data" / "users" / "alice" / "preferences.json"
    assert [item.id for item in LibraryBackend(alice.context).build_library()] == ["alice-tool"]
    assert [item.id for item in LibraryBackend(bob.context).build_library()] == ["bob-tool"]
    assert alice.context.settings.load()["favorites"] == ["alice-tool"]
    assert bob.context.settings.load()["favorites"] == []
    for shared in ("sources", "vault", "vault_key", "shared_settings", "catalog_cache", "slice_environments"):
        assert getattr(alice.context.paths, shared) == getattr(bob.context.paths, shared)


@pytest.mark.parametrize("login", ["CORP\\JSmith", "jsmith@corp.example", "JSmith"])
def test_a_login_name_maps_to_one_profile_folder(tmp_path, monkeypatch, login):
    monkeypatch.setenv("LOGNAME", login)
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))

    assert resolve_app_paths().settings == tmp_path / "data" / "users" / "jsmith" / "preferences.json"


def test_the_first_user_of_an_upgraded_single_user_copy_keeps_its_slices_and_preferences(tmp_path, monkeypatch):
    data = tmp_path / "data"
    install_slice(data / "slices", "owned")
    data.joinpath("preferences.json").write_text(
        json.dumps({"theme": "dark", "favorites": ["owned"], "application_update_source": CUSTOM_UPDATES.__dict__}),
        encoding="utf-8",
    )
    legacy_environment = data / "slice-environments" / "owned" / "0123456789abcdef"
    legacy_environment.mkdir(parents=True)

    owner = open_as("owner", tmp_path, monkeypatch)

    assert not (data / "slices").exists()
    assert not legacy_environment.parent.exists()
    assert [item.id for item in LibraryBackend(owner.context).build_library()] == ["owned"]
    assert owner.context.settings.load()["theme"] == "dark"
    assert owner.context.shared_settings.load()["application_update_source"]["repository_url"] == (
        CUSTOM_UPDATES.repository_url
    )
    colleague = open_as("colleague", tmp_path, monkeypatch)
    assert LibraryBackend(colleague.context).build_library() == []
    assert colleague.context.settings.load()["theme"] == "system"


def test_users_share_sources_tokens_and_the_update_repository(tmp_path, monkeypatch):
    alice = open_as("alice", tmp_path, monkeypatch)
    bob = open_as("bob", tmp_path, monkeypatch)

    alice.add_source(PRIVATE, "private-token")
    bob.add_source(OTHER, "other-token")
    alice.remove_source("private")
    PreferencesBackend(bob.context).configure_application_updates(CUSTOM_UPDATES, "update-token")

    assert alice.context.sources.load() == [OTHER]
    assert alice.context.vault.unlock() == {
        "credentials": {"source:other": "other-token", "application:update": "update-token"}
    }
    assert alice.context.shared_settings.load()["application_update_source"]["repository_url"] == (
        CUSTOM_UPDATES.repository_url
    )
    assert not bob.context.paths.settings.exists()
    with pytest.raises(ValueError, match="Source no longer exists: private"):
        bob.update_source("private", PRIVATE)


def test_preferences_keep_the_update_repository_another_user_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    alice = open_as("alice", tmp_path, monkeypatch)
    bob = open_as("bob", tmp_path, monkeypatch)
    alice_dialog = PreferencesDialog(PreferencesBackend(alice.context))
    bob_dialog = PreferencesDialog(PreferencesBackend(bob.context))
    try:
        alice_dialog.repository_url.selectAll()
        QTest.keyClicks(alice_dialog.repository_url, CUSTOM_UPDATES.repository_url)
        alice_dialog.save()
        bob_dialog.theme.setCurrentIndex(bob_dialog.theme.findData("dark"))
        bob_dialog.save()
    finally:
        alice_dialog.close()
        bob_dialog.close()

    assert bob.context.shared_settings.load()["application_update_source"]["repository_url"] == (
        CUSTOM_UPDATES.repository_url
    )
    assert bob.context.settings.load()["theme"] == "dark"
    assert alice.context.settings.load()["theme"] == "system"
    assert application is not None


def test_editing_a_source_another_user_removed_explains_it(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    alice = open_as("alice", tmp_path, monkeypatch)
    alice.add_source(PRIVATE, "private-token")
    bob = open_as("bob", tmp_path, monkeypatch)
    page = SliceManagerPage(bob)
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args[2]))
    try:
        page.sources.setCurrentItem(page.sources.topLevelItem(0))
        alice.remove_source("private")
        page.edit_source()
    finally:
        page.close()

    assert messages == ["Source no longer exists: private"]
    assert page.sources.topLevelItemCount() == 0
    assert application is not None


def test_slice_packages_take_precedence_over_the_interpreters_own(tmp_path):
    slice_root = tmp_path / "slice"
    slice_root.mkdir()
    slice_root.joinpath("backend.py").write_text(
        "import packaging\nimport dopie_extra\n\n"
        "def run(inputs, progress, log):\n    return [packaging.__version__, dopie_extra.VALUE]\n",
        encoding="utf-8",
    )
    packages = tmp_path / "packages"
    packages.joinpath("packaging").mkdir(parents=True)
    packages.joinpath("packaging", "__init__.py").write_text('__version__ = "from-slice"\n', encoding="utf-8")
    packages.joinpath("extra").mkdir()
    packages.joinpath("extra", "dopie_extra.py").write_text("VALUE = 'from-pth'\n", encoding="utf-8")
    packages.joinpath("extra.pth").write_text("extra\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-I", str(WORKER), str(slice_root), "backend:run", str(packages)],
        input="{}",
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout.splitlines()[-1]) == {"type": "result", "value": ["from-slice", "from-pth"]}


def test_slice_environment_staging_is_published_or_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    manifest = SliceManifest(
        id="packaged",
        name="Packaged",
        version="1.0.0",
        description="Packaged",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(),
        assets=(),
        category="Testing",
        author="Testing",
        license="MIT",
        path=tmp_path,
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", WORKER)
    started = []
    monkeypatch.setattr(widget.process, "start", lambda program, arguments: started.append(arguments))
    monkeypatch.setattr(widget.process, "write", lambda payload: None)
    monkeypatch.setattr(widget.process, "closeWriteChannel", lambda: None)
    packages = tmp_path / "environments" / "linux" / "fingerprint"
    try:
        staging = packages.with_name(".fingerprint-published")
        staging.mkdir(parents=True)
        staging.joinpath("winner").write_text("", encoding="utf-8")
        widget.inputs = {}
        widget.plan = EnvironmentPlan(packages, (), staging)
        widget.phase = "preparing"
        widget.start_next_process()
        assert packages.exists() and not staging.exists()
        assert started[-1][:2] == ["-I", str(WORKER)] and started[-1][-1] == str(packages)

        staging = packages.with_name(".fingerprint-lost")
        staging.mkdir()
        staging.joinpath("loser").write_text("", encoding="utf-8")
        widget.plan = EnvironmentPlan(packages, (), staging)
        widget.phase = "preparing"
        widget.start_next_process()
        assert widget.phase == "running"
        widget.process_finished(0)
        assert packages.joinpath("winner").exists() and not staging.exists()

        widget.plan = EnvironmentPlan(packages.with_name("missing"), (), packages.with_name(".fingerprint-vanished"))
        widget.phase = "preparing"
        widget.run_button.setEnabled(False)
        widget.start_next_process()
        assert widget.status.text().startswith("Failed:")
        assert widget.phase == "idle"
        assert widget.run_button.isEnabled()

        staging = packages.with_name(".fingerprint-failed")
        staging.mkdir()
        widget.plan = EnvironmentPlan(packages.with_name("other"), (), staging)
        widget.phase = "preparing"
        widget.process_finished(1)
        assert not staging.exists()
        assert widget.phase == "idle"
        assert widget.run_button.isEnabled()
    finally:
        widget.close()
    assert application is not None


def test_an_interrupted_adoption_of_the_single_user_layout_is_retried(tmp_path, monkeypatch):
    data = tmp_path / "data"
    install_slice(data / "slices", "owned")
    (data / "slice-environments" / "owned").mkdir(parents=True)
    rmtree = shutil.rmtree
    monkeypatch.setattr(
        shutil, "rmtree", lambda path, *args, **kwargs: (_ for _ in ()).throw(PermissionError(13, "in use"))
    )

    with pytest.raises(PermissionError):
        open_as("owner", tmp_path, monkeypatch)
    assert (data / "slices" / "owned").exists()

    monkeypatch.setattr(shutil, "rmtree", rmtree)
    owner = open_as("owner", tmp_path, monkeypatch)
    assert [item.id for item in LibraryBackend(owner.context).build_library()] == ["owned"]
    assert not (data / "slice-environments" / "owned").exists()


def test_assets_are_prepared_before_dependencies_are_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    tmp_path.joinpath("requirements.lock").write_text("openpyxl==3.1.5 --hash=sha256:0\n", encoding="utf-8")
    manifest = SliceManifest(
        id="with-assets",
        name="With Assets",
        version="1.0.0",
        description="With Assets",
        interface="standard",
        entrypoint=None,
        operation="backend:run",
        inputs=(),
        assets=({"id": "model.bin", "url": "https://example.test/model.bin", "sha256": "0"},),
        category="Testing",
        author="Testing",
        license="MIT",
        path=tmp_path,
    )
    widget = StandardSliceWidget(manifest, tmp_path / "environments", tmp_path / "assets", WORKER)
    monkeypatch.setattr(widget, "start_next_process", lambda: None)
    try:
        widget.start_execution()
        assert [command[3] for command in widget.commands] == ["--prepare-assets", "pip"]
    finally:
        widget.close()
    assert application is not None


def test_a_catalogue_another_user_refreshed_reaches_this_library(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    backend = open_as("alice", tmp_path, monkeypatch)
    backend.add_source(OTHER, "other-token")
    page = SliceManagerPage(backend)
    changes = []
    page.library_changed.connect(lambda: changes.append(True))
    item = {
        "id": "remote",
        "name": "Remote",
        "version": "2.0.0",
        "description": "Remote",
        "download_url": "https://example.test/remote.zip",
        "sha256": "0",
    }
    try:
        backend.context.paths.catalog_cache.joinpath("other.json").write_text(
            json.dumps({"revision": "r", "items": [item]}), encoding="utf-8"
        )
        page.refresh_available_if_stale(15 * 60)
        assert [slice_item.id for slice_item in backend.context.available] == ["remote"]
        assert page.available.topLevelItemCount() == 1
        assert changes == [True]
        page.refresh_available_if_stale(15 * 60)
        assert changes == [True]
    finally:
        page.close()
    assert application is not None


def test_overlapping_source_additions_preserve_both_sources_and_credentials(tmp_path, monkeypatch):
    alice = open_as("alice", tmp_path, monkeypatch)
    bob = open_as("bob", tmp_path, monkeypatch)
    read = Event()
    release = Event()
    attempted = Event()
    load = SourceStore.load

    def pause_first_read(store):
        sources = load(store)
        if current_thread().name.startswith("alice"):
            read.set()
            assert release.wait(5)
        return sources

    def add_bobs_source():
        attempted.set()
        bob.add_source(OTHER, "other-token")

    monkeypatch.setattr(SourceStore, "load", pause_first_read)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="alice") as first:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="bob") as second:
            alice_save = first.submit(alice.add_source, PRIVATE, "private-token")
            try:
                assert read.wait(5)
                bob_save = second.submit(add_bobs_source)
                assert attempted.wait(5)
                with pytest.raises(TimeoutError):
                    bob_save.result(timeout=0.1)
            finally:
                release.set()
            alice_save.result(timeout=5)
            bob_save.result(timeout=5)

    assert {source.id for source in alice.context.sources.load()} == {"private", "other"}
    assert alice.context.vault.unlock() == {
        "credentials": {"source:private": "private-token", "source:other": "other-token"}
    }


def test_concurrent_upgrade_starts_adopt_the_legacy_profile_once(tmp_path):
    data = tmp_path / "data"
    install_slice(data / "slices", "owned")
    data.joinpath("preferences.json").write_text(
        json.dumps({"theme": "dark", "favorites": ["owned"]}), encoding="utf-8"
    )
    data.joinpath("slice-environments", "legacy").mkdir(parents=True)
    script = (
        "import json, sys\nfrom pathlib import Path\n"
        "from dopie.paths import resolve_app_paths\n"
        "from dopie.storage import SettingsStore\n"
        "print('ready', flush=True)\nsys.stdin.readline()\n"
        "paths = resolve_app_paths()\n"
        "print(json.dumps({'slices': [path.name for path in paths.installed_slices.iterdir()], "
        "'preferences': SettingsStore(paths.settings).load()}), flush=True)\n"
    )
    processes = []
    try:
        for user in ("alice", "bob"):
            environment = os.environ.copy()
            environment["LOGNAME"] = user
            environment["DOPIE_ROOT"] = str(tmp_path)
            environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "application" / "base" / "src")
            process = subprocess.Popen(
                [sys.executable, "-c", script],
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(process)
        for process in processes:
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("start\n")
            process.stdin.flush()
        results = []
        for process in processes:
            output, errors = process.communicate(timeout=10)
            assert process.returncode == 0, errors
            results.append(json.loads(output))
        owner = next(result for result in results if result["slices"] == ["owned"])
        colleague = next(result for result in results if result["slices"] == [])
        assert owner["preferences"]["favorites"] == ["owned"]
        assert owner["preferences"]["theme"] == "dark"
        assert colleague["preferences"]["favorites"] == []
        assert colleague["preferences"]["theme"] == "system"
        assert not (data / "slices").exists()
        assert not (data / "slice-environments" / "legacy").exists()
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
