from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from io import BytesIO

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from dopie.models import SourceDefinition
from dopie.sources.remote import RemoteRepositoryClient
from dopie.updates.service import ApplicationUpdateService


def test_prepares_application_update_without_touching_active_source(tmp_path, monkeypatch):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(
            "dopie-next/pyproject.toml",
            '[project]\nname = "dopie"\nversion = "0.2.0"\n',
        )
        package.writestr("dopie-next/src/dopie/__init__.py", '__version__ = "0.2.0"\n')
        package.writestr("dopie-next/src/dopie/application.py", "def main(): return 0\n")
        package.writestr("dopie-next/requirements.lock", "")
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "download_repository_archive",
        lambda self, revision: archive.getvalue(),
    )
    updates = tmp_path / "updates"
    updates.mkdir()
    source = SourceDefinition("dopie", "DoPie", "github", "owner/dopie")

    state = ApplicationUpdateService(updates).prepare_update(source, "abcdef1234")

    assert state["version"] == "0.2.0"
    assert (updates / "prepared" / "src" / "dopie" / "__init__.py").exists()
    assert json.loads((updates / "pending.json").read_text(encoding="utf-8"))["revision"] == "abcdef1234"


def test_signed_application_update_authenticates_archive(tmp_path, monkeypatch):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("dopie-next/pyproject.toml", '[project]\nname="dopie"\nversion="0.2.0"')
        package.writestr("dopie-next/src/dopie/application.py", "def main(): return 0\n")
        package.writestr("dopie-next/requirements.lock", "")
    payload = archive.getvalue()
    revision = "abcdef1234"
    release = json.dumps({"revision": revision, "sha256": hashlib.sha256(payload).hexdigest()}).encode()
    private_key = Ed25519PrivateKey.generate()
    signature = base64.b64encode(private_key.sign(release))
    public_key = base64.b64encode(private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    monkeypatch.setattr(RemoteRepositoryClient, "download_repository_archive", lambda self, value: payload)
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "read_repository_file",
        lambda self, path, value=None: signature if path.endswith(".sig") else release,
    )
    source = SourceDefinition("dopie", "DoPie", "github", "owner/dopie", public_key=public_key)

    state = ApplicationUpdateService(tmp_path).prepare_update(source, revision)

    assert state["revision"] == revision
