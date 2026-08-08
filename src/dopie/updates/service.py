from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tempfile
import tomllib
import zipfile
from io import BytesIO
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from dopie.models import SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient


class ApplicationUpdateService:
    def __init__(self, updates: Path):
        self.updates = updates

    def check_for_update(
        self,
        source: SourceDefinition,
        installed_revision: str | None,
        token: str | None = None,
    ) -> str | None:
        revision = RemoteRepositoryClient(source, token).resolve_revision()
        self.authenticate_release(source, revision, token)
        return revision if revision != installed_revision else None

    def authenticate_release(
        self,
        source: SourceDefinition,
        revision: str,
        token: str | None = None,
    ) -> dict[str, str]:
        if not source.public_key:
            return {}
        client = RemoteRepositoryClient(source, token)
        manifest = client.read_repository_file("update.json", revision)
        signature = client.read_repository_file("update.json.sig", revision)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(source.public_key)).verify(
            base64.b64decode(signature.strip()), manifest
        )
        release = json.loads(manifest)
        if release.get("revision") != revision or not release.get("sha256"):
            raise ValueError("Signed update metadata does not match the resolved revision")
        return {"revision": str(release["revision"]), "sha256": str(release["sha256"])}

    def prepare_update(self, source: SourceDefinition, revision: str, token: str | None = None) -> dict[str, str]:
        archive = RemoteRepositoryClient(source, token).download_repository_archive(revision)
        release = self.authenticate_release(source, revision, token)
        if release and hashlib.sha256(archive).hexdigest() != release["sha256"].removeprefix("sha256:"):
            raise ValueError("Application update archive checksum verification failed")
        with tempfile.TemporaryDirectory(prefix="dopie-update-") as temporary:
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
