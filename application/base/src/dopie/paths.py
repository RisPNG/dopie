from __future__ import annotations

import getpass
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from dopie.shared_folder import shared_folder_transaction


@dataclass(frozen=True)
class AppPaths:
    project: Path
    active_project: Path
    data: Path
    bundled_slices: Path
    installed_slices: Path
    slice_environments: Path
    slice_assets: Path
    catalog_cache: Path
    settings: Path
    shared_settings: Path
    sources: Path
    vault: Path
    vault_key: Path
    updates: Path
    changelog: Path
    portable: bool


def resolve_app_paths() -> AppPaths:
    source_project = Path(__file__).resolve().parents[2]
    default_project = source_project.parents[1] if source_project.name == "base" else source_project
    project = Path(os.environ.get("DOPIE_ROOT", default_project)).resolve()
    default_active_project = project / "application" / "base"
    if not default_active_project.exists():
        default_active_project = project
    active_project = Path(os.environ.get("DOPIE_ACTIVE_ROOT", default_active_project)).resolve()
    portable = True
    data = project / "data"
    data.mkdir(parents=True, exist_ok=True)
    user = data / "users" / getpass.getuser().rpartition("\\")[2].partition("@")[0].casefold()
    installed_slices = user / "slices"
    slice_environments = (
        Path(os.environ["LOCALAPPDATA"]) / "DoPie"
        if sys.platform == "win32"
        else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "dopie"
    ) / "slice-environments"
    slice_assets = data / "slice-assets"
    catalog_cache = data / "catalog-cache"
    updates = data / "updates"
    legacy_slices = data / "slices"
    with shared_folder_transaction(data / ".configuration.lock"):
        if legacy_slices.exists() and not installed_slices.exists():
            user.mkdir(parents=True, exist_ok=True)
            if (data / "preferences.json").exists():
                shutil.copyfile(data / "preferences.json", user / "preferences.json")
            if (data / "slice-environments").exists():
                shutil.rmtree(data / "slice-environments")
            legacy_slices.rename(installed_slices)
        installed_slices.mkdir(parents=True, exist_ok=True)
        slice_assets.mkdir(exist_ok=True)
        catalog_cache.mkdir(exist_ok=True)
        updates.mkdir(exist_ok=True)
    return AppPaths(
        project=project,
        active_project=active_project,
        data=data,
        bundled_slices=active_project / "slices",
        installed_slices=installed_slices,
        slice_environments=slice_environments,
        slice_assets=slice_assets,
        catalog_cache=catalog_cache,
        settings=user / "preferences.json",
        shared_settings=data / "preferences.json",
        sources=data / "sources.json",
        vault=data / "source-vault.dopie",
        vault_key=data / "source-vault.key",
        updates=updates,
        changelog=active_project / "changelog",
        portable=portable,
    )
