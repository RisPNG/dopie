from __future__ import annotations

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
