from __future__ import annotations

import errno
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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


@pytest.mark.parametrize(
    "recorded",
    ["Z:\\Else\\DoPie\\data\\updates\\prepared-12345678", "/mnt/other/DoPie/data/updates/prepared-12345678"],
)
def test_activates_an_update_prepared_through_another_path(tmp_path, bootstrap, recorded):
    base = application_folder(tmp_path / "application" / "base")
    prepared = tmp_path / "data" / "updates" / "prepared-12345678"
    prepared.mkdir(parents=True)
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


def test_a_concurrent_launch_does_not_activate_the_same_update_twice(tmp_path, bootstrap, monkeypatch):
    application_folder(tmp_path / "application" / "base")
    destination = application_folder(tmp_path / "application" / "versions" / "0.2.0-12345678")
    current_path = tmp_path / "application" / "current.json"
    current = {"version": "0.2.0", "revision": "1234567890", "path": str(destination), "previous": {"path": "base"}}
    current_path.write_text(json.dumps(current), encoding="utf-8")
    prepared = tmp_path / "data" / "updates" / "prepared-12345678"
    prepared.mkdir(parents=True)
    pending = prepared.parent / "pending.json"
    pending.write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
    )

    assert bootstrap.activate_prepared_update(tmp_path) == (destination, False)

    assert not prepared.exists()
    assert not pending.exists()
    assert json.loads(current_path.read_text(encoding="utf-8")) == current


def test_losing_the_activation_race_to_another_launch_is_not_an_error(tmp_path, bootstrap, monkeypatch):
    application_folder(tmp_path / "application" / "base")
    destination = tmp_path / "application" / "versions" / "0.2.0-12345678"
    prepared = tmp_path / "data" / "updates" / "prepared-12345678"
    prepared.mkdir(parents=True)
    prepared.parent.joinpath("pending.json").write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}), encoding="utf-8"
    )

    def lose_race(self, target):
        application_folder(Path(target))
        raise OSError(errno.ENOTEMPTY, "Directory not empty")

    monkeypatch.setattr(Path, "rename", lose_race)

    assert bootstrap.activate_prepared_update(tmp_path) == (destination, True)
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
    monkeypatch.setattr(bootstrap, "activate_prepared_update", lambda root: (current, True))
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

    monkeypatch.setattr(bootstrap, "activate_prepared_update", lambda root: (current, False))
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
    assert prepared == [(tmp_path, application)]


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

    assert packages.parent == tmp_path / "environments" / ("windows" if sys.platform == "win32" else "linux")
    assert packages.joinpath("installed").exists()
    assert commands[0][:5] == [sys.executable, "-I", "-m", "pip", "install"]
    assert "--no-cache-dir" in commands[0] and "--require-hashes" in commands[0]
    assert Path(commands[0][commands[0].index("--target") + 1]).parent == packages.parent
    assert [path.name for path in packages.parent.iterdir()] == [packages.name]
    assert bootstrap.prepare_application_environment(tmp_path, application) == packages
    assert len(commands) == 1


def test_application_package_builds_clean_up_after_losing_a_race_or_failing(tmp_path, bootstrap, monkeypatch):
    application = application_folder(tmp_path / "application" / "base")
    environments = tmp_path / "environments" / ("windows" if sys.platform == "win32" else "linux")

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
    prepared = tmp_path / "data" / "updates" / "prepared-12345678"
    prepared.mkdir(parents=True)
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

    monkeypatch.setattr(Path, "replace", replace)
    destination = tmp_path / "application" / "versions" / "0.2.0-12345678"
    assert bootstrap.activate_prepared_update(tmp_path) == (destination, True)
    assert not pending.exists()
