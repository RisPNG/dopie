from __future__ import annotations

import os
import stat

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
