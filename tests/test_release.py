from __future__ import annotations

import tomllib
from pathlib import Path

from dopie import __version__
from dopie.changelog.backend import ChangelogReader


def test_release_metadata_and_notes_match():
    project = Path(__file__).parents[1] / "application" / "base"
    with project.joinpath("pyproject.toml").open("rb") as stream:
        metadata_version = str(tomllib.load(stream)["project"]["version"])

    assert __version__ == metadata_version == "1.0.0"
    assert ChangelogReader(project / "changelog").release_notes_since("0.1.0", __version__).startswith(
        "# DoPie 1.0.0"
    )
