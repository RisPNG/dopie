from __future__ import annotations

import os
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.exceptions import InvalidTag

from dopie.security.vault import VaultStore


def test_vault_round_trip(tmp_path):
    vault = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")
    secrets = {"credentials": {"source:private": "token-value"}}

    vault.seal(secrets)

    assert vault.unlock() == secrets
    assert "token-value" not in vault.path.read_text(encoding="utf-8")


def test_transferred_vault_requires_password_once(tmp_path):
    source = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")
    source.seal({"credentials": {"source:private": "token-value"}})
    transferred = source.export_for_transfer("correct password")
    destination = VaultStore(tmp_path / "imported-vault.dopie", tmp_path / "imported-vault.key")

    with pytest.raises(InvalidTag):
        destination.import_from_transfer(transferred, "wrong password")

    destination.import_from_transfer(transferred, "correct password")

    assert destination.unlock() == {"credentials": {"source:private": "token-value"}}
    assert destination.key_path.exists()


def test_new_vault_key_is_shared_only_with_the_folders_group(tmp_path):
    vault = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")
    previous = os.umask(0o002)
    try:
        vault.store_source_credential("source:private", "token-value")
    finally:
        os.umask(previous)

    if os.name == "posix":
        assert stat.S_IMODE(vault.key_path.stat().st_mode) == 0o660
    assert vault.source_credential("source:private") == "token-value"


def test_vault_key_and_vault_do_not_share_a_temporary_file(tmp_path):
    tmp_path.joinpath("source-vault.tmp").mkdir()
    vault = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")

    vault.store_source_credential("source:private", "token-value")

    assert vault.unlock() == {"credentials": {"source:private": "token-value"}}
    assert not list(tmp_path.glob("source-vault.*.tmp"))


def test_credential_changes_keep_credentials_added_by_another_user(tmp_path):
    first = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")
    second = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")

    first.store_source_credential("source:first", "first-token")
    second.store_source_credential("source:second", "second-token")

    assert first.source_credential("source:second") == "second-token"
    first.remove_source_credential("source:first")
    assert second.unlock() == {"credentials": {"source:second": "second-token"}}
    second.store_source_credential("source:second", "rotated-token")
    assert first.source_credential("source:second") == "rotated-token"
    assert first.source_credential(None) is None


def test_users_create_one_vault_and_keep_all_concurrent_credentials(tmp_path, monkeypatch):
    start = threading.Barrier(8)
    generated_keys = []
    urandom = os.urandom

    def generate(length):
        if length == 32:
            generated_keys.append(True)
            time.sleep(0.02)
        return urandom(length)

    def add_credential(index):
        start.wait(timeout=5)
        VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key").store_source_credential(
            f"source:{index}", f"token-{index}"
        )

    monkeypatch.setattr(os, "urandom", generate)
    with ThreadPoolExecutor(max_workers=8) as users:
        list(users.map(add_credential, range(8)))

    vault = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")
    assert vault.unlock() == {"credentials": {f"source:{index}": f"token-{index}" for index in range(8)}}
    assert generated_keys == [True]
    assert not list(tmp_path.glob("*.tmp"))


def test_users_keep_each_others_concurrent_changes_to_an_existing_vault(tmp_path, monkeypatch):
    vault = VaultStore(tmp_path / "source-vault.dopie", tmp_path / "source-vault.key")
    vault.store_source_credential("source:existing", "original")
    key = vault.key_path.read_bytes()
    start = threading.Barrier(8)
    unlock = VaultStore.unlock

    def read_credentials(self):
        secrets = unlock(self)
        time.sleep(0.01)
        return secrets

    def add_credential(index):
        start.wait(timeout=5)
        VaultStore(vault.path, vault.key_path).store_source_credential(f"source:{index}", f"token-{index}")

    monkeypatch.setattr(VaultStore, "unlock", read_credentials)
    with ThreadPoolExecutor(max_workers=8) as users:
        list(users.map(add_credential, range(8)))

    assert vault.unlock() == {
        "credentials": {"source:existing": "original", **{f"source:{index}": f"token-{index}" for index in range(8)}}
    }
    assert vault.key_path.read_bytes() == key
