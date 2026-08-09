from __future__ import annotations

import json
import zipfile

import pytest

from dopie.paths import resolve_app_paths
from dopie.provisioning.backend import ProvisioningBackend
from dopie.security.vault import VaultStore
from dopie.sources.profile import PortableProfileService


def test_public_profile_is_applied_only_once(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    monkeypatch.setenv("DOPIE_ROOT", str(source_root))
    source_paths = resolve_app_paths()
    source_paths.sources.write_text("[]", encoding="utf-8")
    profile = destination_root / "provisioning" / "DoPie.dopie-profile"
    profile.parent.mkdir()
    PortableProfileService(source_paths).export_portable_profile(profile, include_slices=False)
    monkeypatch.setenv("DOPIE_ROOT", str(destination_root))
    destination_paths = resolve_app_paths()
    backend = ProvisioningBackend(destination_paths)

    pending = backend.pending_provisioning()
    backend.apply_provisioning(pending)

    assert backend.pending_provisioning() is None
    assert not profile.exists()
    assert json.loads(destination_paths.sources.read_text(encoding="utf-8")) == []


def test_changed_private_profile_requires_authorization_again(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    monkeypatch.setenv("DOPIE_ROOT", str(source_root))
    source_paths = resolve_app_paths()
    source_paths.sources.write_text("[]", encoding="utf-8")
    VaultStore(source_paths.vault, source_paths.vault_key).seal(
        {"credentials": {"source:private": "private-token"}}
    )
    profile = destination_root / "provisioning" / "DoPie.dopie-profile"
    profile.parent.mkdir()
    PortableProfileService(source_paths).export_portable_profile(
        profile,
        include_slices=False,
        password="transfer password",
    )
    monkeypatch.setenv("DOPIE_ROOT", str(destination_root))
    destination_paths = resolve_app_paths()
    backend = ProvisioningBackend(destination_paths)
    pending = backend.pending_provisioning()

    with pytest.raises(Exception):
        backend.apply_provisioning(pending, "wrong password")
    assert profile.exists()
    assert not destination_paths.data.joinpath("provisioning.json").exists()

    backend.apply_provisioning(pending, "transfer password")
    assert backend.pending_provisioning() is None
    assert not profile.exists()
    assert VaultStore(destination_paths.vault, destination_paths.vault_key).unlock()["credentials"] == {
        "source:private": "private-token"
    }
    PortableProfileService(source_paths).export_portable_profile(
        profile,
        include_slices=False,
        password="replacement password",
    )
    assert backend.pending_provisioning().requires_password


def test_corrupt_profile_and_receipt_do_not_destroy_existing_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    paths = resolve_app_paths()
    paths.sources.write_text('[{"existing":true}]', encoding="utf-8")
    paths.data.joinpath("provisioning.json").write_text("not json", encoding="utf-8")
    profile = tmp_path / "provisioning" / "DoPie.dopie-profile"
    profile.parent.mkdir()
    profile.write_text("not a zip", encoding="utf-8")

    with pytest.raises(zipfile.BadZipFile):
        ProvisioningBackend(paths).pending_provisioning()

    assert paths.sources.read_text(encoding="utf-8") == '[{"existing":true}]'
