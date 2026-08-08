from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from dopie.security.vault import VaultStore


def test_vault_round_trip(tmp_path):
    vault = VaultStore(tmp_path / "source-vault.dopie")
    secrets = {"credentials": {"source:private": "token-value"}}

    vault.seal(secrets, "correct horse battery staple")

    assert vault.unlock("correct horse battery staple") == secrets
    assert "token-value" not in vault.path.read_text(encoding="utf-8")


def test_vault_rejects_wrong_password(tmp_path):
    vault = VaultStore(tmp_path / "source-vault.dopie")
    vault.seal({"credentials": {}}, "correct password")

    with pytest.raises(InvalidTag):
        vault.unlock("wrong password")
