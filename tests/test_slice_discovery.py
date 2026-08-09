from __future__ import annotations

import pytest

from dopie.slices.discovery import SliceDiscovery

MANIFEST = """
id = "demo-slice"
name = "Demo Slice"
version = "1.0.0"
description = "Count text"
entrypoint = "frontend:SliceWidget"
"""


def test_discovers_bundled_and_installed_slices(tmp_path):
    bundled = tmp_path / "bundled"
    installed = tmp_path / "installed"
    (bundled / "demo_slice").mkdir(parents=True)
    (bundled / "demo_slice" / "slice.toml").write_text(MANIFEST, encoding="utf-8")
    installed.mkdir()

    manifests = SliceDiscovery(bundled, installed).discover_installed_slices()

    assert [manifest.id for manifest in manifests] == ["demo-slice"]


def test_rejects_duplicate_slice_ids(tmp_path):
    bundled = tmp_path / "bundled"
    installed = tmp_path / "installed"
    (bundled / "one").mkdir(parents=True)
    (installed / "two").mkdir(parents=True)
    (bundled / "one" / "slice.toml").write_text(MANIFEST, encoding="utf-8")
    (installed / "two" / "slice.toml").write_text(MANIFEST, encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate Slice id"):
        SliceDiscovery(bundled, installed).discover_installed_slices()
