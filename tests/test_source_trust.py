from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from dopie.models import SourceDefinition
from dopie.paths import resolve_app_paths
from dopie.sources.catalog import SourceCatalog
from dopie.sources.profile import PortableProfileService
from dopie.sources.remote import RemoteRepositoryClient


def test_signed_source_catalog_is_verified(monkeypatch):
    payload = json.dumps(
        {
            "slices": [
                {
                    "id": "tool",
                    "name": "Tool",
                    "version": "1.0.0",
                    "description": "Tool",
                    "download_url": "https://example.test/tool.zip",
                    "sha256": "abc",
                }
            ]
        }
    ).encode()
    private_key = Ed25519PrivateKey.generate()
    signature = base64.b64encode(private_key.sign(payload))
    public_key = base64.b64encode(private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    monkeypatch.setattr(RemoteRepositoryClient, "resolve_revision", lambda self: "revision")
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "read_repository_file",
        lambda self, path, revision=None: signature if path.endswith(".sig") else payload,
    )
    source = SourceDefinition("source", "Source", "github", "owner/repository", public_key=public_key)

    items = SourceCatalog().fetch_available_slices(source)

    assert [item.id for item in items] == ["tool"]


def test_portable_profile_moves_encrypted_sources_and_installed_slices(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    for root in (source_root, destination_root):
        (root / "portable.toml").write_text('mode="portable"', encoding="utf-8")
    monkeypatch.setenv("DOPIE_ROOT", str(source_root))
    source_paths = resolve_app_paths()
    source_paths.sources.write_text('[{"id":"private"}]', encoding="utf-8")
    source_paths.vault.write_bytes(b"encrypted-vault")
    installed = source_paths.installed_slices / "tool" / "versions" / "1.0.0"
    installed.mkdir(parents=True)
    installed.joinpath("slice.toml").write_text("installed", encoding="utf-8")
    profile = tmp_path / "portable.dopie-profile"
    PortableProfileService(source_paths).export_portable_profile(profile)

    monkeypatch.setenv("DOPIE_ROOT", str(destination_root))
    destination_paths = resolve_app_paths()
    PortableProfileService(destination_paths).import_portable_profile(profile)

    assert destination_paths.vault.read_bytes() == b"encrypted-vault"
    assert (destination_paths.installed_slices / "tool" / "versions" / "1.0.0" / "slice.toml").exists()
