from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_activates_prepared_application_version(tmp_path):
    path = Path(__file__).parents[1] / "bootstrap" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("dopie_bootstrap", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    prepared = tmp_path / "data" / "updates" / "prepared"
    prepared.mkdir(parents=True)
    prepared.joinpath("pyproject.toml").write_text("prepared", encoding="utf-8")
    pending = prepared.parent / "pending.json"
    pending.write_text(
        json.dumps({"version": "0.2.0", "revision": "1234567890", "path": str(prepared)}),
        encoding="utf-8",
    )

    active = module.activate_prepared_update(tmp_path)

    assert active == tmp_path / "application" / "versions" / "0.2.0-12345678"
    assert active.joinpath("pyproject.toml").read_text(encoding="utf-8") == "prepared"
    assert not pending.exists()


def test_restores_previous_application_after_failed_startup(tmp_path):
    path = Path(__file__).parents[1] / "bootstrap" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("dopie_bootstrap_rollback", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    previous.mkdir()
    current.mkdir()
    application = tmp_path / "application"
    application.mkdir()
    application.joinpath("current.json").write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "revision": "new",
                "path": str(current),
                "previous": {"version": "1.0.0", "revision": "old", "path": str(previous)},
            }
        ),
        encoding="utf-8",
    )

    restored = module.restore_previous_application(tmp_path)

    assert restored == previous
    state = json.loads(application.joinpath("current.json").read_text(encoding="utf-8"))
    assert state["version"] == "1.0.0"


def test_failed_early_startup_rolls_back_but_clean_exit_does_not(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "bootstrap" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("dopie_bootstrap_health", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    current.mkdir()
    previous.mkdir()
    launches = iter([(1, False), (0, True)])
    restored: list[Path] = []
    monkeypatch.setattr(module, "activate_prepared_update", lambda root: current)
    monkeypatch.setattr(module, "prepare_application_environment", lambda root, application: application / "python")
    monkeypatch.setattr(module, "launch_application", lambda root, application, python: next(launches))
    monkeypatch.setattr(module, "restore_previous_application", lambda root: restored.append(root) or previous)

    assert module.main(tmp_path) == 0
    assert restored == [tmp_path]

    monkeypatch.setattr(module, "launch_application", lambda root, application, python: (0, False))
    restored.clear()

    assert module.main(tmp_path) == 0
    assert restored == []
