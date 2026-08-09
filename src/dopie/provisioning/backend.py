from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from dopie.paths import AppPaths
from dopie.sources.profile import PortableProfileService


@dataclass(frozen=True)
class PendingProvisioning:
    profile: Path
    digest: str
    requires_password: bool


class ProvisioningBackend:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def pending_provisioning(self) -> PendingProvisioning | None:
        profile = self.paths.project / "DoPie.dopie-profile"
        if not profile.exists():
            return None
        digest = hashlib.sha256(profile.read_bytes()).hexdigest()
        receipt = self.paths.data / "provisioning.json"
        provisioned_digest = None
        if receipt.exists():
            try:
                provisioned_digest = json.loads(receipt.read_text(encoding="utf-8")).get("profile_sha256")
            except json.JSONDecodeError:
                provisioned_digest = None
        if provisioned_digest == digest:
            return None
        return PendingProvisioning(
            profile,
            digest,
            PortableProfileService(self.paths).profile_requires_password(profile),
        )

    def apply_provisioning(self, pending: PendingProvisioning, password: str | None = None) -> None:
        PortableProfileService(self.paths).import_portable_profile(pending.profile, password)
        receipt = self.paths.data / "provisioning.json"
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps({"profile_sha256": pending.digest}, indent=2), encoding="utf-8")
        temporary.replace(receipt)
