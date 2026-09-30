from __future__ import annotations

import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

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
    PortableProfileService(source_paths).export_portable_profile(profile)
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


def test_simultaneous_starts_apply_a_shared_profile_only_once(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path / "source"))
    source_paths = resolve_app_paths()
    VaultStore(source_paths.vault, source_paths.vault_key).store_source_credential("source:private", "token")
    profile = tmp_path / "shared" / "provisioning" / "DoPie.dopie-profile"
    profile.parent.mkdir(parents=True)
    PortableProfileService(source_paths).export_portable_profile(profile)
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path / "shared"))
    monkeypatch.setenv("LOGNAME", "alice")
    alice_paths = resolve_app_paths()
    alice = ProvisioningBackend(alice_paths)
    monkeypatch.setenv("LOGNAME", "bob")
    bob_paths = resolve_app_paths()
    bob = ProvisioningBackend(bob_paths)
    pending = [(alice, alice.pending_provisioning()), (bob, bob.pending_provisioning())]
    start = threading.Barrier(2)
    imported = []
    import_profile = PortableProfileService.import_portable_profile

    def import_once(self, source, password=None):
        imported.append(self.paths.settings)
        import_profile(self, source, password)

    def launch(item):
        backend, authorization = item
        start.wait(timeout=5)
        backend.apply_provisioning(authorization)

    monkeypatch.setattr(PortableProfileService, "import_portable_profile", import_once)
    with ThreadPoolExecutor(max_workers=2) as users:
        list(users.map(launch, pending))

    assert len(imported) == 1
    assert sum(path.exists() for path in (alice_paths.settings, bob_paths.settings)) == 1
    assert not profile.exists()
    assert alice.pending_provisioning() is None
    assert bob.pending_provisioning() is None
    assert VaultStore(alice_paths.vault, alice_paths.vault_key).unlock() == {
        "credentials": {"source:private": "token"}
    }
    assert json.loads((alice_paths.data / "provisioning.json").read_text(encoding="utf-8"))[
        "profile_sha256"
    ] == pending[0][1].digest


def test_a_profile_replaced_while_authorization_is_pending_is_not_imported(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    paths = resolve_app_paths()
    profile = tmp_path / "provisioning" / "DoPie.dopie-profile"
    profile.parent.mkdir()
    service = PortableProfileService(paths)
    service.export_portable_profile(profile)
    backend = ProvisioningBackend(paths)
    pending = backend.pending_provisioning()
    with zipfile.ZipFile(profile, "a") as archive:
        archive.writestr("replacement", "replacement")

    with pytest.raises(ValueError, match="profile changed"):
        backend.apply_provisioning(pending)

    assert profile.exists()
    assert not paths.sources.exists()
    assert not (paths.data / "provisioning.json").exists()
