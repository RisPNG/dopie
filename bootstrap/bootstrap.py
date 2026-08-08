from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import venv
from pathlib import Path


def activate_prepared_update(root: Path) -> Path:
    application = root / "application"
    current_path = application / "current.json"
    pending_path = root / "data" / "updates" / "pending.json"
    if pending_path.exists():
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        prepared = Path(pending["path"])
        destination = application / "versions" / f"{pending['version']}-{pending['revision'][:8]}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(prepared, destination)
        if current_path.exists():
            previous = json.loads(current_path.read_text(encoding="utf-8"))
        else:
            project_file = root / "pyproject.toml"
            if project_file.exists():
                with project_file.open("rb") as stream:
                    previous_version = str(tomllib.load(stream)["project"]["version"])
            else:
                previous_version = "unknown"
            previous = {"version": previous_version, "revision": None, "path": str(root)}
        current = {
            "version": pending["version"],
            "revision": pending["revision"],
            "path": str(destination),
            "previous": previous,
        }
        current_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        pending_path.unlink()
    if current_path.exists():
        return Path(json.loads(current_path.read_text(encoding="utf-8"))["path"])
    return root


def prepare_application_environment(root: Path, application: Path) -> Path:
    lock = application / "requirements.lock"
    fingerprint = hashlib.sha256(
        f"{sys.version_info.major}.{sys.version_info.minor}\n".encode("ascii") + lock.read_bytes()
    ).hexdigest()[:16]
    environment = root / "environments" / fingerprint
    if sys.platform == "win32":
        python = environment / "Scripts" / "python.exe"
    else:
        python = environment / "bin" / "python"
    marker = environment / ".ready"
    if not marker.exists():
        if environment.exists():
            shutil.rmtree(environment)
        venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "-r",
                str(lock),
            ],
            check=True,
        )
        marker.write_text("ready", encoding="utf-8")
    return python


def launch_application(root: Path, application: Path, python: Path) -> tuple[int, bool]:
    marker = root / "data" / "updates" / "startup-healthy"
    marker.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["DOPIE_ROOT"] = str(root)
    environment["DOPIE_ACTIVE_ROOT"] = str(application)
    environment["DOPIE_STARTUP_MARKER"] = str(marker)
    environment["PYTHONPATH"] = str(application / "src")
    returncode = subprocess.run([str(python), "-m", "dopie.application"], env=environment).returncode
    return returncode, marker.exists()


def restore_previous_application(root: Path) -> Path | None:
    current_path = root / "application" / "current.json"
    if not current_path.exists():
        return None
    current = json.loads(current_path.read_text(encoding="utf-8"))
    previous = current.get("previous")
    if not previous:
        return None
    current_path.write_text(json.dumps(previous, indent=2), encoding="utf-8")
    return Path(previous["path"])


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    application = activate_prepared_update(root)
    try:
        python = prepare_application_environment(root, application)
        returncode, healthy = launch_application(root, application, python)
    except Exception:
        previous = restore_previous_application(root)
        if previous is None:
            raise
        python = prepare_application_environment(root, previous)
        return launch_application(root, previous, python)[0]
    if healthy:
        return returncode
    previous = restore_previous_application(root)
    if previous is None:
        return returncode
    python = prepare_application_environment(root, previous)
    return launch_application(root, previous, python)[0]


if __name__ == "__main__":
    raise SystemExit(main())
