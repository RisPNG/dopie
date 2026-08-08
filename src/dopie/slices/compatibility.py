from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from dopie.models import CatalogSlice, SliceManifest


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    reason: str = ""


def evaluate_slice_compatibility(item: CatalogSlice | SliceManifest, api_version: int = 1) -> CompatibilityResult:
    if item.api_version != api_version:
        return CompatibilityResult(False, f"Requires Pie API {item.api_version}")
    python_version = Version(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    if python_version not in SpecifierSet(item.python):
        return CompatibilityResult(False, f"Requires Python {item.python}")
    if item.platforms and sys.platform not in item.platforms:
        return CompatibilityResult(False, f"Not available on {sys.platform}")
    architecture = platform.machine().casefold()
    if item.architectures and architecture not in {value.casefold() for value in item.architectures}:
        return CompatibilityResult(False, f"Not available for {architecture}")
    return CompatibilityResult(True)
