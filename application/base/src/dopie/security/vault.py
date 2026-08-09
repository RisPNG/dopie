from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


class VaultStore:
    def __init__(self, path: Path, key_path: Path):
        self.path = path
        self.key_path = key_path

    def seal(self, secrets: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.exists():
            key = base64.b64decode(self.key_path.read_text(encoding="ascii"))
        else:
            key = os.urandom(32)
            temporary_key = self.key_path.with_suffix(".tmp")
            temporary_key.write_text(base64.b64encode(key).decode("ascii"), encoding="ascii")
            temporary_key.chmod(0o600)
            temporary_key.replace(self.key_path)
        nonce = os.urandom(12)
        header = {
            "format": "dopie-source-vault",
            "version": 2,
            "cipher": "aes-256-gcm",
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        authenticated = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(
            nonce,
            json.dumps(secrets, separators=(",", ":")).encode("utf-8"),
            authenticated,
        )
        header["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(header, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def unlock(self) -> dict[str, Any]:
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        if envelope.get("format") != "dopie-source-vault" or envelope.get("version") != 2:
            raise ValueError("Unsupported Source vault")
        ciphertext = base64.b64decode(envelope.pop("ciphertext"))
        nonce = base64.b64decode(envelope["nonce"])
        key = base64.b64decode(self.key_path.read_text(encoding="ascii"))
        authenticated = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, authenticated)
        return json.loads(plaintext)

    def export_for_transfer(self, password: str) -> bytes:
        salt = os.urandom(16)
        nonce = os.urandom(12)
        iterations = 3
        lanes = 4
        memory_cost = 64 * 1024
        key = Argon2id(
            salt=salt,
            length=32,
            iterations=iterations,
            lanes=lanes,
            memory_cost=memory_cost,
        ).derive(password.encode("utf-8"))
        header = {
            "format": "dopie-transfer-vault",
            "version": 1,
            "kdf": "argon2id",
            "iterations": iterations,
            "lanes": lanes,
            "memory_cost": memory_cost,
            "salt": base64.b64encode(salt).decode("ascii"),
            "cipher": "aes-256-gcm",
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        authenticated = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(
            nonce,
            json.dumps(self.unlock(), separators=(",", ":")).encode("utf-8"),
            authenticated,
        )
        header["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        return json.dumps(header, indent=2).encode("utf-8")

    def import_from_transfer(self, payload: bytes, password: str) -> None:
        envelope = json.loads(payload)
        if envelope.get("format") != "dopie-transfer-vault" or envelope.get("version") != 1:
            raise ValueError("Unsupported transferred Source vault")
        ciphertext = base64.b64decode(envelope.pop("ciphertext"))
        nonce = base64.b64decode(envelope["nonce"])
        key = Argon2id(
            salt=base64.b64decode(envelope["salt"]),
            length=32,
            iterations=int(envelope["iterations"]),
            lanes=int(envelope["lanes"]),
            memory_cost=int(envelope["memory_cost"]),
        ).derive(password.encode("utf-8"))
        authenticated = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, authenticated)
        self.key_path.unlink(missing_ok=True)
        self.seal(json.loads(plaintext))
