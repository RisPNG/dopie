from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid
from pathlib import Path, PureWindowsPath


def recorded_application(root: Path, recorded: str) -> Path:
    base = root / "application" / "base"
    name = PureWindowsPath(recorded).name
    application = base if name == "base" else root / "application" / "versions" / name
    return application if (application / "requirements.lock").exists() else base


def activate_prepared_update(root: Path) -> tuple[Path, bool]:
    application = root / "application"
    base = application / "base"
    current_path = application / "current.json"
    pending_path = root / "data" / "updates" / "pending.json"
    current = json.loads(current_path.read_text(encoding="utf-8")) if current_path.exists() else None
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pending = None
    if pending is not None:
        destination = application / "versions" / f"{pending['version']}-{pending['revision'][:8]}"
        prepared = root / "data" / "updates" / PureWindowsPath(pending["path"]).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            prepared.rename(destination)
        except OSError:
            if not destination.exists():
                raise
            shutil.rmtree(prepared, ignore_errors=True)
        activated = current is None or recorded_application(root, current["path"]) != destination
        if activated:
            if current is None:
                previous_path = base if base.exists() else root
                project_file = previous_path / "pyproject.toml"
                if project_file.exists():
                    with project_file.open("rb") as stream:
                        previous_version = str(tomllib.load(stream)["project"]["version"])
                else:
                    previous_version = "unknown"
                current = {"version": previous_version, "revision": None, "path": str(previous_path)}
            state = {
                "version": pending["version"],
                "revision": pending["revision"],
                "path": str(destination),
                "previous": current,
            }
            temporary = current_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temporary.replace(current_path)
        pending_path.unlink(missing_ok=True)
        return destination, activated
    if current is not None:
        return recorded_application(root, current["path"]), False
    return (base if base.exists() else root), False


def prepare_application_environment(root: Path, application: Path) -> Path:
    lock = application / "requirements.lock"
    fingerprint = hashlib.sha256(
        f"{sys.version_info.major}.{sys.version_info.minor}\n".encode("ascii") + lock.read_bytes()
    ).hexdigest()[:16]
    environment = root / "environments" / ("windows" if sys.platform == "win32" else "linux") / fingerprint
    if not environment.exists():
        environment.parent.mkdir(parents=True, exist_ok=True)
        staging = environment.with_name(f".{fingerprint}-{uuid.uuid4().hex[:8]}")
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-cache-dir",
                    "--require-hashes",
                    "--target",
                    str(staging),
                    "-r",
                    str(lock),
                ],
                check=True,
            )
            staging.rename(environment)
        except OSError:
            if not environment.exists():
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return environment


def launch_application(root: Path, application: Path, packages: Path) -> tuple[int, bool]:
    marker = Path(tempfile.gettempdir()) / f"dopie-{uuid.uuid4().hex}.healthy"
    environment = os.environ.copy()
    environment["DOPIE_ROOT"] = str(root)
    environment["DOPIE_ACTIVE_ROOT"] = str(application)
    environment["DOPIE_STARTUP_MARKER"] = str(marker)
    environment["PYTHONPATH"] = os.pathsep.join((str(application / "src"), str(packages)))
    returncode = subprocess.run([sys.executable, "-s", "-P", "-m", "dopie.application"], env=environment).returncode
    healthy = marker.exists()
    marker.unlink(missing_ok=True)
    return returncode, healthy


def restore_previous_application(root: Path, failed: Path) -> Path | None:
    current_path = root / "application" / "current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    previous = current.get("previous")
    if not previous or recorded_application(root, current["path"]) != failed:
        return None
    temporary = current_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(previous, indent=2), encoding="utf-8")
    temporary.replace(current_path)
    return recorded_application(root, previous["path"])


def main(root: Path | None = None, prepare_only: bool = False) -> int:
    root = root or Path(__file__).resolve().parent.parent
    application, activated = activate_prepared_update(root)
    try:
        packages = prepare_application_environment(root, application)
        if prepare_only:
            return 0
        returncode, healthy = launch_application(root, application, packages)
    except Exception:
        previous = restore_previous_application(root, application) if activated else None
        if previous is None:
            raise
        packages = prepare_application_environment(root, previous)
        if prepare_only:
            return 0
        return launch_application(root, previous, packages)[0]
    if returncode == 0 or healthy or not activated:
        return returncode
    previous = restore_previous_application(root, application)
    if previous is None:
        return returncode
    packages = prepare_application_environment(root, previous)
    return launch_application(root, previous, packages)[0]


if __name__ == "__main__":
    raise SystemExit(main(prepare_only="--prepare-only" in sys.argv[1:]))
