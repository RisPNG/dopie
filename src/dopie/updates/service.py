from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from io import BytesIO
from pathlib import Path

from dopie.models import SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient


class ApplicationUpdateService:
    def __init__(self, updates: Path, state: Path, active_application: Path):
        self.updates = updates
        self.state = state
        self.active_application = active_application

    def check_for_update(
        self,
        source: SourceDefinition,
        token: str | None = None,
    ) -> str | None:
        revision = RemoteRepositoryClient(source, token).resolve_revision()
        recorded_revision = None
        if self.state.exists():
            recorded_revision = json.loads(self.state.read_text(encoding="utf-8")).get("revision")
        installed_revision = recorded_revision
        if (self.active_application / ".git").exists() and shutil.which("git"):
            installed_revision = subprocess.run(
                ["git", "-C", str(self.active_application), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        elif installed_revision is None:
            installed_revision = revision
        if recorded_revision != installed_revision:
            with (self.active_application / "pyproject.toml").open("rb") as stream:
                version = str(tomllib.load(stream)["project"]["version"])
            self.state.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.state.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "version": version,
                        "revision": installed_revision,
                        "path": str(self.active_application),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.state)
        return revision if revision != installed_revision else None

    def prepare_update(self, source: SourceDefinition, revision: str, token: str | None = None) -> dict[str, str]:
        archive = RemoteRepositoryClient(source, token).download_repository_archive(revision)
        with tempfile.TemporaryDirectory(prefix="dopie-update-", dir=self.updates) as temporary:
            extracted = Path(temporary) / "archive"
            extracted.mkdir()
            with zipfile.ZipFile(BytesIO(archive)) as package:
                root = extracted.resolve()
                for member in package.infolist():
                    destination = (extracted / member.filename).resolve()
                    if not destination.is_relative_to(root):
                        raise ValueError(f"Unsafe update member: {member.filename}")
                package.extractall(extracted)
            candidates = list(extracted.rglob("pyproject.toml"))
            if len(candidates) != 1:
                raise ValueError("DoPie update must contain one pyproject.toml")
            project = candidates[0].parent
            for required in ("requirements.lock", "src/dopie/application.py"):
                if not (project / required).is_file():
                    raise ValueError(f"DoPie update is missing {required}")
            with candidates[0].open("rb") as stream:
                version = str(tomllib.load(stream)["project"]["version"])
            prepared = self.updates / "prepared"
            if prepared.exists():
                shutil.rmtree(prepared)
            shutil.copytree(project, prepared)
        state = {"version": version, "revision": revision, "path": str(prepared)}
        (self.updates / "pending.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state
