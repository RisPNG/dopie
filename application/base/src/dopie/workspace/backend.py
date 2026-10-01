from __future__ import annotations

import hashlib
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from dopie.models import SliceManifest


@dataclass(frozen=True)
class EnvironmentPlan:
    packages: Path | None
    commands: tuple[tuple[str, ...], ...]
    staging: Path | None = None


class SliceEnvironmentManager:
    def __init__(self, environments: Path):
        self.environments = environments

    def prepare_slice_environment(self, manifest: SliceManifest) -> EnvironmentPlan:
        lock = manifest.path / "requirements.lock"
        if not lock.exists():
            return EnvironmentPlan(None, ())
        fingerprint = hashlib.sha256(
            f"{sys.version_info.major}.{sys.version_info.minor}\n".encode("ascii") + lock.read_bytes()
        ).hexdigest()[:16]
        environment = self.environments / fingerprint
        if environment.exists():
            return EnvironmentPlan(environment, ())
        environment.parent.mkdir(parents=True, exist_ok=True)
        staging = environment.with_name(f".{fingerprint}-{uuid.uuid4().hex[:8]}")
        return EnvironmentPlan(
            environment,
            (
                (
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
                ),
            ),
            staging,
        )
