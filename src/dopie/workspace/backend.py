from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from dopie.models import SliceManifest


@dataclass(frozen=True)
class EnvironmentPlan:
    python: Path
    commands: tuple[tuple[str, ...], ...]
    marker: Path | None = None


class SliceEnvironmentManager:
    def __init__(self, environments: Path):
        self.environments = environments

    def prepare_slice_environment(self, manifest: SliceManifest) -> EnvironmentPlan:
        lock = manifest.path / "requirements.lock"
        dependency_data = lock.read_bytes() if lock.exists() else b""
        fingerprint = hashlib.sha256(
            f"{sys.version_info.major}.{sys.version_info.minor}\n".encode("ascii") + dependency_data
        ).hexdigest()[:16]
        environment = self.environments / manifest.id / fingerprint
        if sys.platform == "win32":
            python = environment / "Scripts" / "python.exe"
        else:
            python = environment / "bin" / "python"
        marker = environment / ".ready"
        if marker.exists() and python.exists():
            return EnvironmentPlan(python, (), marker)
        environment.parent.mkdir(parents=True, exist_ok=True)
        commands: tuple[tuple[str, ...], ...] = ((sys.executable, "-m", "venv", str(environment)),)
        if lock.exists():
            commands += (
                (
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--require-hashes",
                    "-r",
                    str(lock),
                ),
            )
        return EnvironmentPlan(python, commands, marker)
