from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


class VaultStore:
    def __init__(self, path: Path):
        self.path = path

    def seal(self, secrets: dict[str, Any], password: str) -> None:
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
            "format": "dopie-source-vault",
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
            json.dumps(secrets, separators=(",", ":")).encode("utf-8"),
            authenticated,
        )
        header["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(header, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def unlock(self, password: str) -> dict[str, Any]:
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        ciphertext = base64.b64decode(envelope.pop("ciphertext"))
        salt = base64.b64decode(envelope["salt"])
        nonce = base64.b64decode(envelope["nonce"])
        key = Argon2id(
            salt=salt,
            length=32,
            iterations=int(envelope["iterations"]),
            lanes=int(envelope["lanes"]),
            memory_cost=int(envelope["memory_cost"]),
        ).derive(password.encode("utf-8"))
        authenticated = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, authenticated)
        return json.loads(plaintext)
