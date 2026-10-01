from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def bootstrap(request):
    path = Path(__file__).parents[1] / "bootstrap" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location(f"dopie_bootstrap_{request.node.name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def application_folder(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("requirements.lock").write_text("", encoding="utf-8")
    return path


def test_bootstrap_loads_without_application_sources(tmp_path, bootstrap):
    isolated = tmp_path / "bootstrap.py"
    isolated.write_text(Path(bootstrap.__file__).read_text(encoding="utf-8"), encoding="utf-8")

    loaded = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "import runpy, sys; runpy.run_path(sys.argv[1]); "
            "print(any(name == 'dopie' or name.startswith('dopie.') for name in sys.modules))",
            str(isolated),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert loaded.stdout.strip() == "False"


@pytest.mark.parametrize(
    "recorded",
    ["Z:\\Else\\DoPie\\data\\updates\\prepared-12345678", "/mnt/other/DoPie/data/updates/prepared-12345678"],
)
def test_activates_an_update_prepared_through_another_path(tmp_path, bootstrap, recorded):
    base = application_folder(tmp_path / "application" / "base")
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
    prepared.joinpath("pyproject.toml").write_text("prepared", encoding="utf-8")
    pending = prepared.parent / "pending.json"
    pending.write_text(json.dumps({"version": "0.2.0", "revision": "1234567890", "path": recorded}), encoding="utf-8")

    active, activated = bootstrap.activate_prepared_update(tmp_path)

    assert active == tmp_path / "application" / "versions" / "0.2.0-12345678"
    assert activated
    assert active.joinpath("pyproject.toml").read_text(encoding="utf-8") == "prepared"
    assert not pending.exists()
    current = json.loads((tmp_path / "application" / "current.json").read_text(encoding="utf-8"))
    assert current["path"] == str(active)
    assert current["previous"]["path"] == str(base)


def test_an_already_activated_update_does_not_change_its_previous_version(tmp_path, bootstrap):
    application_folder(tmp_path / "application" / "base")
    destination = application_folder(tmp_path / "application" / "versions" / "0.2.0-12345678")
    current_path = tmp_path / "application" / "current.json"
    current = {"version": "0.2.0", "revision": "1234567890", "path": str(destination), "previous": {"path": "base"}}
    current_path.write_text(json.dumps(current), encoding="utf-8")
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
    pending = prepared.parent / "pending.json"
    pending.write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
    )

    assert bootstrap.activate_prepared_update(tmp_path) == (destination, False)

    assert not prepared.exists()
    assert not pending.exists()
    assert json.loads(current_path.read_text(encoding="utf-8")) == current


def test_concurrent_threads_activate_a_pending_update_once(tmp_path, bootstrap):
    base = application_folder(tmp_path / "application" / "base")
    destination = tmp_path / "application" / "versions" / "0.2.0-12345678"
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
    prepared.parent.joinpath("pending.json").write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
    )

    ready = threading.Barrier(2)

    def launch():
        ready.wait(timeout=10)
        return bootstrap.activate_prepared_update(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        launches = [executor.submit(launch) for _ in range(2)]
        outcomes = [launch.result(timeout=10) for launch in launches]

    assert sorted(activated for _, activated in outcomes) == [False, True]
    assert all(application == destination for application, _ in outcomes)
    assert not prepared.exists()
    current = json.loads((tmp_path / "application" / "current.json").read_text(encoding="utf-8"))
    assert current["previous"]["path"] == str(base)


def test_concurrent_processes_activate_a_pending_update_once(tmp_path, bootstrap):
    base = application_folder(tmp_path / "application" / "base")
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
    prepared.parent.joinpath("pending.json").write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
    )
    program = """
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("bootstrap", sys.argv[1])
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
print("ready", flush=True)
sys.stdin.readline()
application, activated = bootstrap.activate_prepared_update(Path(sys.argv[2]))
print(json.dumps([str(application), activated]), flush=True)
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", program, bootstrap.__file__, str(tmp_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("start\n")
            process.stdin.flush()
        outcomes = []
        for process in processes:
            output, error = process.communicate(timeout=10)
            assert process.returncode == 0, error
            outcomes.append(json.loads(output))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

    assert sorted(activated for _, activated in outcomes) == [False, True]
    destination = tmp_path / "application" / "versions" / "0.2.0-12345678"
    assert all(application == str(destination) for application, _ in outcomes)
    current = json.loads((tmp_path / "application" / "current.json").read_text(encoding="utf-8"))
    assert current["previous"]["path"] == str(base)
    assert not prepared.exists()


def test_uses_the_nested_base_application_before_the_first_update(tmp_path, bootstrap):
    base = application_folder(tmp_path / "application" / "base")

    assert bootstrap.activate_prepared_update(tmp_path) == (base, False)

    current = tmp_path / "application" / "current.json"
    current.write_text(
        json.dumps({"version": "0.1.0", "revision": "current", "path": str(tmp_path)}),
        encoding="utf-8",
    )

    assert bootstrap.activate_prepared_update(tmp_path) == (base, False)


def test_recorded_versions_resolve_inside_the_folder_this_launch_uses(tmp_path, bootstrap):
    base = application_folder(tmp_path / "application" / "base")
    version = application_folder(tmp_path / "application" / "versions" / "1.2.0-abcd1234")

    unc = "\\\\server\\tools\\DoPie\\application\\versions\\1.2.0-abcd1234"
    assert bootstrap.recorded_application(tmp_path, unc) == version
    assert bootstrap.recorded_application(tmp_path, "/mnt/dopie/application/base") == base
    assert bootstrap.recorded_application(tmp_path, "/mnt/dopie/application/versions/9.9.9-missing") == base
    assert bootstrap.recorded_application(tmp_path, str(tmp_path)) == base


def test_restores_previous_application_only_while_it_is_still_current(tmp_path, bootstrap):
    base = application_folder(tmp_path / "application" / "base")
    failed = application_folder(tmp_path / "application" / "versions" / "2.0.0-new")
    current_path = tmp_path / "application" / "current.json"
    current = {
        "version": "2.0.0",
        "revision": "new",
        "path": "Z:\\Else\\DoPie\\application\\versions\\2.0.0-new",
        "previous": {"version": "1.0.0", "revision": "old", "path": "/mnt/other/DoPie/application/base"},
    }
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert bootstrap.restore_previous_application(tmp_path, base) is None
    assert json.loads(current_path.read_text(encoding="utf-8")) == current

    assert bootstrap.restore_previous_application(tmp_path, failed) == base
    assert json.loads(current_path.read_text(encoding="utf-8"))["version"] == "1.0.0"
    assert bootstrap.restore_previous_application(tmp_path, base) is None


def test_only_the_launch_that_activated_an_update_rolls_it_back(tmp_path, bootstrap, monkeypatch):
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    launches = iter([(1, False), (0, True)])
    restored: list[Path] = []
    monkeypatch.setattr(bootstrap, "activate_prepared_update", lambda root, prepare_only=False: (current, True))
    monkeypatch.setattr(bootstrap, "prepare_application_environment", lambda root, application: application / "lib")
    monkeypatch.setattr(bootstrap, "launch_application", lambda root, application, packages: next(launches))
    monkeypatch.setattr(
        bootstrap, "restore_previous_application", lambda root, failed: restored.append(failed) or previous
    )

    assert bootstrap.main(tmp_path) == 0
    assert restored == [current]

    restored.clear()
    monkeypatch.setattr(bootstrap, "launch_application", lambda root, application, packages: (0, False))
    assert bootstrap.main(tmp_path) == 0
    assert restored == []

    monkeypatch.setattr(bootstrap, "activate_prepared_update", lambda root, prepare_only=False: (current, False))
    monkeypatch.setattr(bootstrap, "launch_application", lambda root, application, packages: (1, False))
    assert bootstrap.main(tmp_path) == 1
    assert restored == []

    monkeypatch.setattr(
        bootstrap,
        "prepare_application_environment",
        lambda root, application: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "pip")),
    )
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.main(tmp_path)
    assert restored == []


def test_prepare_only_builds_environment_without_launching_application(tmp_path, bootstrap, monkeypatch):
    application = application_folder(tmp_path / "application" / "base")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    prepared: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        bootstrap, "prepare_application_environment", lambda root, active: prepared.append((root, active))
    )
    monkeypatch.setattr(
        bootstrap,
        "launch_application",
        lambda root, active, packages: pytest.fail("prepare-only mode launched the application"),
    )

    assert bootstrap.main(tmp_path, prepare_only=True) == 0
    assert prepared == [(tmp_path / "cache" / ("DoPie" if sys.platform == "win32" else "dopie"), application)]


def test_prepare_only_preserves_a_pending_update_for_startup_and_rollback(tmp_path, bootstrap, monkeypatch):
    base = application_folder(tmp_path / "application" / "base")
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
    pending = prepared.parent / "pending.json"
    state = {"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}
    pending.write_text(json.dumps(state), encoding="utf-8")
    prepared_applications = []
    launches = []
    destination = tmp_path / "application" / "versions" / "0.2.0-12345678"
    monkeypatch.setattr(
        bootstrap,
        "prepare_application_environment",
        lambda root, application: prepared_applications.append(application) or application,
    )

    def launch(root, application, packages):
        launches.append(application)
        return (1, False) if application == destination else (0, True)

    monkeypatch.setattr(bootstrap, "launch_application", launch)

    assert bootstrap.main(tmp_path, prepare_only=True) == 0
    assert prepared_applications == [base]
    assert prepared.exists()
    assert json.loads(pending.read_text(encoding="utf-8")) == state
    assert not launches

    assert bootstrap.main(tmp_path) == 0
    assert launches == [destination, base]
    assert prepared_applications == [base, destination, base]
    assert not pending.exists()
    current = json.loads((tmp_path / "application" / "current.json").read_text(encoding="utf-8"))
    assert current["path"] == str(base)


def test_rollback_finishes_before_a_new_update_activates(tmp_path, bootstrap, monkeypatch):
    base = application_folder(tmp_path / "application" / "base")
    failed = application_folder(tmp_path / "application" / "versions" / "0.2.0-12345678")
    current_path = tmp_path / "application" / "current.json"
    current_path.write_text(
        json.dumps({"version": "0.2.0", "path": str(failed), "previous": {"path": str(base)}}), encoding="utf-8"
    )
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-abcdef12")
    prepared.parent.joinpath("pending.json").write_text(
        json.dumps({"version": "0.3.0", "revision": "abcdef1234", "path": str(prepared)}), encoding="utf-8"
    )
    rollback_publishing = threading.Event()
    activation_attempted = threading.Event()
    activation_finished = threading.Event()
    replace = Path.replace

    def publish(self, destination):
        if Path(destination) == current_path and json.loads(self.read_text(encoding="utf-8"))["path"] == str(base):
            rollback_publishing.set()
            assert activation_attempted.wait(timeout=5)
            assert not activation_finished.wait(timeout=0.1)
        return replace(self, destination)

    def activate():
        assert rollback_publishing.wait(timeout=5)
        activation_attempted.set()
        outcome = bootstrap.activate_prepared_update(tmp_path)
        activation_finished.set()
        return outcome

    monkeypatch.setattr(Path, "replace", publish)
    with ThreadPoolExecutor(max_workers=2) as executor:
        rollback = executor.submit(bootstrap.restore_previous_application, tmp_path, failed)
        activation = executor.submit(activate)
        assert rollback.result(timeout=5) == base
        destination, activated = activation.result(timeout=5)

    assert activated
    assert activation_finished.is_set()
    assert current_path.exists()
    current = json.loads(current_path.read_text(encoding="utf-8"))
    assert current["path"] == str(destination)
    assert current["previous"]["path"] == str(base)
    assert bootstrap.restore_previous_application(tmp_path, failed) is None
    assert json.loads(current_path.read_text(encoding="utf-8")) == current


def test_application_packages_are_built_once_into_a_relocatable_folder(tmp_path, bootstrap, monkeypatch):
    application = application_folder(tmp_path / "application" / "base")
    commands: list[list[str]] = []

    def install(command, check):
        commands.append(command)
        target = Path(command[command.index("--target") + 1])
        target.mkdir()
        target.joinpath("installed").write_text("", encoding="utf-8")

    monkeypatch.setattr(bootstrap.subprocess, "run", install)

    packages = bootstrap.prepare_application_environment(tmp_path, application)

    assert packages.parent == tmp_path / "environments"
    assert packages.joinpath("installed").exists()
    assert commands[0][:5] == [sys.executable, "-I", "-m", "pip", "install"]
    assert "--no-cache-dir" in commands[0] and "--require-hashes" in commands[0]
    assert Path(commands[0][commands[0].index("--target") + 1]).parent == packages.parent
    assert [path.name for path in packages.parent.iterdir()] == [packages.name]
    assert bootstrap.prepare_application_environment(tmp_path, application) == packages
    assert len(commands) == 1


def test_application_package_builds_clean_up_after_losing_a_race_or_failing(tmp_path, bootstrap, monkeypatch):
    application = application_folder(tmp_path / "application" / "base")
    environments = tmp_path / "environments"

    def lose_race(command, check):
        target = Path(command[command.index("--target") + 1])
        target.mkdir()
        target.joinpath("mine").write_text("", encoding="utf-8")
        winner = target.with_name(target.name.split("-")[0].lstrip("."))
        winner.mkdir()
        winner.joinpath("theirs").write_text("", encoding="utf-8")

    monkeypatch.setattr(bootstrap.subprocess, "run", lose_race)
    packages = bootstrap.prepare_application_environment(tmp_path, application)
    assert packages.joinpath("theirs").exists()
    assert [path.name for path in environments.iterdir()] == [packages.name]

    application.joinpath("requirements.lock").write_text("changed", encoding="utf-8")

    def fail(command, check):
        Path(command[command.index("--target") + 1]).mkdir()
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(bootstrap.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.prepare_application_environment(tmp_path, application)
    assert [path.name for path in environments.iterdir()] == [packages.name]


def test_each_launch_reports_its_health_through_its_own_local_marker(tmp_path, bootstrap, monkeypatch):
    application = application_folder(tmp_path / "application" / "base")
    packages = tmp_path / "environments" / "linux" / "fingerprint"
    launches: list[tuple[list[str], dict[str, str]]] = []

    def launch(command, env):
        launches.append((command, env))
        Path(env["DOPIE_STARTUP_MARKER"]).write_text("healthy", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", launch)

    assert bootstrap.launch_application(tmp_path, application, packages) == (0, True)
    assert bootstrap.launch_application(tmp_path, application, packages) == (0, True)

    (first_command, first), (_, second) = launches
    assert first_command == [sys.executable, "-s", "-P", "-m", "dopie.application"]
    assert first["DOPIE_STARTUP_MARKER"] != second["DOPIE_STARTUP_MARKER"]
    assert Path(first["DOPIE_STARTUP_MARKER"]).parent == Path(tempfile.gettempdir())
    assert not Path(first["DOPIE_STARTUP_MARKER"]).exists()
    assert first["PYTHONPATH"].split(os.pathsep) == [str(application / "src"), str(packages)]
    assert first["DOPIE_ROOT"] == str(tmp_path)
    assert first["DOPIE_ACTIVE_ROOT"] == str(application)


def test_an_update_whose_switch_failed_is_completed_by_the_next_launch(tmp_path, bootstrap, monkeypatch):
    application_folder(tmp_path / "application" / "base")
    prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
    pending = prepared.parent / "pending.json"
    pending.write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
    )
    replace = Path.replace

    def locked(self, target):
        if Path(target).name == "current.json":
            raise PermissionError(13, "The file is being used by another process")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", locked)
    with pytest.raises(PermissionError):
        bootstrap.activate_prepared_update(tmp_path)
    assert pending.exists()
    assert not list((tmp_path / "application").glob("current.*.tmp"))

    monkeypatch.setattr(Path, "replace", replace)
    destination = tmp_path / "application" / "versions" / "0.2.0-12345678"
    assert bootstrap.activate_prepared_update(tmp_path) == (destination, True)
    assert not pending.exists()


@pytest.mark.parametrize("operation", ["activate", "restore"])
@pytest.mark.parametrize("fail_publication", [False, True])
def test_windows_update_transactions_unlock_their_handle_after_publication(
    tmp_path, bootstrap, monkeypatch, operation, fail_publication
):
    base = application_folder(tmp_path / "application" / "base")
    project = base / "pyproject.toml"
    project.write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    current_path = base.parent / "current.json"
    destination = base.parent / "versions" / "0.2.0-12345678"
    if operation == "activate":
        prepared = application_folder(tmp_path / "data" / "updates" / "prepared-12345678")
        prepared.parent.joinpath("pending.json").write_text(
            json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
        )
    else:
        application_folder(destination)
        current_path.write_text(
            json.dumps({"version": "0.2.0", "path": str(destination), "previous": {"path": str(base)}}),
            encoding="utf-8",
        )
    calls = []
    project_handles = []

    def locking(handle, mode, length):
        calls.append((handle, mode, length, os.fstat(handle).st_ino))

    open_file = Path.open

    def open_path(self, *args, **kwargs):
        stream = open_file(self, *args, **kwargs)
        if self == project:
            project_handles.append(stream.fileno())
        return stream

    replace = Path.replace

    def publish(self, target):
        if fail_publication and Path(target) == current_path:
            raise PermissionError("current application is locked")
        return replace(self, target)

    monkeypatch.setattr(bootstrap, "os", SimpleNamespace(name="nt"))
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=locking, LK_NBLCK="acquire", LK_UNLCK="release"))
    monkeypatch.setattr(Path, "open", open_path)
    monkeypatch.setattr(Path, "replace", publish)
    if fail_publication:
        with pytest.raises(PermissionError, match="current application is locked"):
            if operation == "activate":
                bootstrap.activate_prepared_update(tmp_path)
            else:
                bootstrap.restore_previous_application(tmp_path, destination)
    elif operation == "activate":
        assert bootstrap.activate_prepared_update(tmp_path) == (destination, True)
    else:
        assert bootstrap.restore_previous_application(tmp_path, destination) == base

    assert [(mode, length) for _, mode, length, _ in calls] == [("acquire", 1), ("release", 1)]
    assert calls[0][0] == calls[1][0]
    assert {inode for _, _, _, inode in calls} == {(base.parent / ".updates.lock").stat().st_ino}
    if operation == "activate":
        assert len(project_handles) == 1
        assert project_handles[0] != calls[0][0]
    assert not list(base.parent.glob("current.*.tmp"))
