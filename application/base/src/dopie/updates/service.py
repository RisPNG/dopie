from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
import uuid
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path, PureWindowsPath

from dopie.models import SourceDefinition
from dopie.shared_folder import shared_folder_transaction
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
        checkout = next(
            (
                path
                for path in (self.active_application, *self.active_application.parents)
                if (path / ".git").exists()
                and self.active_application in (path, path / "application" / "base")
            ),
            None,
        )
        with shared_folder_transaction(self.state.parent / ".updates.lock"):
            current = json.loads(self.state.read_text(encoding="utf-8")) if self.state.exists() else None
            recorded_revision = current.get("revision") if current is not None else None
            selected_application = self.active_application
            if current is not None:
                selected_application = Path(current["path"])
                if selected_application.resolve() != self.active_application.resolve():
                    recorded = PureWindowsPath(current["path"])
                    if recorded.name == "base":
                        selected_application = self.state.parent / "base"
                    elif recorded.parent.name == "versions":
                        selected_application = self.state.parent / "versions" / recorded.name
            selected_active = selected_application.resolve() == self.active_application.resolve()
            installed_revision = recorded_revision
            if selected_active and checkout is not None and shutil.which("git"):
                installed_revision = subprocess.run(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            elif installed_revision is None:
                installed_revision = revision
            if selected_active and recorded_revision != installed_revision:
                with (self.active_application / "pyproject.toml").open("rb") as stream:
                    version = str(tomllib.load(stream)["project"]["version"])
                temporary = self.state.with_suffix(f".{uuid.uuid4().hex}.tmp")
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

    def prepare_update(
        self,
        source: SourceDefinition,
        revision: str,
        token: str | None = None,
        progress: Callable[[int], None] | None = None,
    ) -> dict[str, str]:
        pending = self.updates / "pending.json"
        prepared = self.updates / f"prepared-{revision[:8]}"
        with shared_folder_transaction(self.state.parent / ".updates.lock"):
            if self.state.exists():
                current = json.loads(self.state.read_text(encoding="utf-8"))
                if current.get("revision") == revision:
                    return {key: current[key] for key in ("version", "revision", "path")}
            if pending.exists() and prepared.exists():
                state = json.loads(pending.read_text(encoding="utf-8"))
                if state["revision"] == revision:
                    return state
        client = RemoteRepositoryClient(source, token)
        archive = (
            client.download_repository_archive(revision)
            if progress is None
            else client.download_repository_archive(revision, progress)
        )
        staging = self.updates / f"dopie-update-{uuid.uuid4().hex[:8]}"
        staging.mkdir()
        try:
            extracted = staging / "archive"
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
            with shared_folder_transaction(self.state.parent / ".updates.lock"):
                if self.state.exists():
                    current = json.loads(self.state.read_text(encoding="utf-8"))
                    if current.get("revision") == revision:
                        return {key: current[key] for key in ("version", "revision", "path")}
                if pending.exists() and prepared.exists():
                    state = json.loads(pending.read_text(encoding="utf-8"))
                    if state["revision"] == revision:
                        return state
                if not prepared.exists():
                    project.rename(prepared)
                state = {"version": version, "revision": revision, "path": str(prepared)}
                temporary_state = pending.with_suffix(f".{uuid.uuid4().hex}.tmp")
                temporary_state.write_text(json.dumps(state, indent=2), encoding="utf-8")
                temporary_state.replace(pending)
                return state
        finally:
            shutil.rmtree(staging, ignore_errors=True)
