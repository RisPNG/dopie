from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


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
    sources: Path
    vault: Path
    updates: Path
    changelog: Path
    portable: bool


def resolve_app_paths() -> AppPaths:
    project = Path(os.environ.get("DOPIE_ROOT", Path(__file__).resolve().parents[2])).resolve()
    active_project = Path(os.environ.get("DOPIE_ACTIVE_ROOT", project)).resolve()
    portable = (project / "portable.toml").is_file()
    if portable:
        data = project / "data"
    elif sys.platform == "win32":
        data = Path(os.environ["APPDATA"]) / "DoPie"
    else:
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "dopie"
    data.mkdir(parents=True, exist_ok=True)
    installed_slices = data / "slices"
    slice_environments = data / "slice-environments"
    slice_assets = data / "slice-assets"
    catalog_cache = data / "catalog-cache"
    updates = data / "updates"
    installed_slices.mkdir(exist_ok=True)
    slice_environments.mkdir(exist_ok=True)
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
        settings=data / "preferences.json",
        sources=data / "sources.json",
        vault=data / "source-vault.dopie",
        updates=updates,
        changelog=active_project / "changelog",
        portable=portable,
    )
