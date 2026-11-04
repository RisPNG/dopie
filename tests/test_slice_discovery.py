from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from dopie.models import SliceManifest
from dopie.shared_folder import shared_folder_transaction
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


def test_bundled_and_different_sources_can_share_a_slice_id(tmp_path):
    bundled = tmp_path / "bundled" / "demo"
    bundled.mkdir(parents=True)
    bundled.joinpath("slice.toml").write_text(MANIFEST, encoding="utf-8")
    installed = tmp_path / "installed"
    for source_id in ("maintained", "community"):
        root = installed / "sources" / source_id / "demo-slice"
        version = root / "versions" / "1.0.0"
        version.mkdir(parents=True)
        version.joinpath("slice.toml").write_text(MANIFEST, encoding="utf-8")
        root.joinpath("current.json").write_text(
            json.dumps({"version": "1.0.0", "source_id": source_id}), encoding="utf-8"
        )

    manifests = SliceDiscovery(bundled.parent, installed).discover_installed_slices()

    assert {manifest.key for manifest in manifests} == {
        "demo-slice", "maintained/demo-slice", "community/demo-slice"
    }
    assert {manifest.source_id for manifest in manifests} == {None, "maintained", "community"}


def test_rejects_duplicate_identities_within_one_source(tmp_path):
    installed = tmp_path / "installed"
    for folder in ("one", "two"):
        root = installed / "sources" / "source" / folder
        version = root / "versions" / "1.0.0"
        version.mkdir(parents=True)
        version.joinpath("slice.toml").write_text(MANIFEST, encoding="utf-8")
        root.joinpath("current.json").write_text(
            '{"version": "1.0.0", "source_id": "source"}', encoding="utf-8"
        )

    with pytest.raises(ValueError, match="Duplicate Slice id: source/demo-slice"):
        SliceDiscovery(tmp_path / "bundled", installed).discover_installed_slices()


def test_discovery_migrates_all_legacy_versions_and_keeps_local_slices(tmp_path):
    installed = tmp_path / "installed"
    legacy = installed / "demo-slice"
    for version in ("1.0.0", "2.0.0"):
        root = legacy / "versions" / version
        root.mkdir(parents=True)
        root.joinpath("slice.toml").write_text(MANIFEST.replace("1.0.0", version), encoding="utf-8")
        root.joinpath("backend.py").write_text(f"VERSION = '{version}'\n", encoding="utf-8")
    legacy.joinpath("current.json").write_text(
        '{"version": "2.0.0", "source_id": "source"}', encoding="utf-8"
    )
    local = installed / "local"
    local.mkdir()
    local.joinpath("slice.toml").write_text(MANIFEST.replace("demo-slice", "local"), encoding="utf-8")
    discovery = SliceDiscovery(tmp_path / "bundled", installed)

    manifests = discovery.discover_installed_slices()

    assert {manifest.key for manifest in manifests} == {"source/demo-slice", "local"}
    migrated = installed / "sources" / "source" / "demo-slice"
    assert not legacy.exists()
    assert json.loads(migrated.joinpath("current.json").read_text()) == {
        "version": "2.0.0", "source_id": "source"
    }
    for version in ("1.0.0", "2.0.0"):
        assert migrated.joinpath("versions", version, "backend.py").read_text() == f"VERSION = '{version}'\n"
    assert discovery.discover_installed_slices() == manifests
    assert not (installed / ".legacy-slices").exists()


def test_migration_handles_legacy_slice_ids_that_match_storage_namespaces(tmp_path):
    installed = tmp_path / "installed"
    for slice_id, source_id in (("sources", "local"), ("local", "sources")):
        root = installed / slice_id
        version = root / "versions" / "1.0.0"
        version.mkdir(parents=True)
        version.joinpath("slice.toml").write_text(MANIFEST.replace("demo-slice", slice_id), encoding="utf-8")
        root.joinpath("current.json").write_text(
            json.dumps({"version": "1.0.0", "source_id": source_id}), encoding="utf-8"
        )

    manifests = SliceDiscovery(tmp_path / "bundled", installed).discover_installed_slices()

    assert {manifest.key for manifest in manifests} == {"local/sources", "sources/local"}
    assert installed.joinpath("sources", "local", "sources", "versions", "1.0.0", "slice.toml").exists()
    assert installed.joinpath("sources", "sources", "local", "versions", "1.0.0", "slice.toml").exists()


def test_migration_preserves_both_directories_when_destination_is_occupied(tmp_path):
    installed = tmp_path / "installed"
    for root in (installed / "demo-slice", installed / "sources" / "source" / "demo-slice"):
        version = root / "versions" / "1.0.0"
        version.mkdir(parents=True)
        version.joinpath("slice.toml").write_text(MANIFEST, encoding="utf-8")
        root.joinpath("current.json").write_text(
            '{"version": "1.0.0", "source_id": "source"}', encoding="utf-8"
        )
    before = {path: path.read_bytes() for path in installed.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="migration destination already exists"):
        SliceDiscovery(tmp_path / "bundled", installed).discover_installed_slices()

    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert not installed.joinpath(".legacy-slices").exists()


def test_discovery_resumes_a_staged_legacy_migration(tmp_path):
    installed = tmp_path / "installed"
    root = installed / ".legacy-slices" / "demo-slice"
    version = root / "versions" / "1.0.0"
    version.mkdir(parents=True)
    version.joinpath("slice.toml").write_text(MANIFEST, encoding="utf-8")
    root.joinpath("current.json").write_text(
        '{"version": "1.0.0", "source_id": "source"}', encoding="utf-8"
    )

    manifests = SliceDiscovery(tmp_path / "bundled", installed).discover_installed_slices()

    assert [manifest.key for manifest in manifests] == ["source/demo-slice"]
    assert manifests[0].path == installed / "sources" / "source" / "demo-slice" / "versions" / "1.0.0"
    assert not installed.joinpath(".legacy-slices").exists()


def test_source_rename_waits_for_discovery_to_finish_reading_installed_manifests(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    source_root = installed / "sources" / "source"
    root = source_root / "demo-slice"
    version = root / "versions" / "1.0.0"
    version.mkdir(parents=True)
    version.joinpath("slice.toml").write_text(MANIFEST, encoding="utf-8")
    root.joinpath("current.json").write_text(
        '{"version": "1.0.0", "source_id": "source"}', encoding="utf-8"
    )
    reading = Event()
    release = Event()
    attempted = Event()
    load_manifest = SliceManifest.load

    def load_during_rename(cls, path, **kwargs):
        if path.is_relative_to(installed) and not release.is_set():
            reading.set()
            assert release.wait(5)
        return load_manifest(path, **kwargs)

    def rename_source():
        attempted.set()
        with shared_folder_transaction(installed / ".configuration.lock"):
            destination = installed / "sources" / "renamed"
            source_root.rename(destination)
            destination.joinpath("demo-slice", "current.json").write_text(
                '{"version": "1.0.0", "source_id": "renamed"}', encoding="utf-8"
            )

    monkeypatch.setattr(SliceManifest, "load", classmethod(load_during_rename))
    discovery = SliceDiscovery(tmp_path / "bundled", installed)
    with ThreadPoolExecutor(max_workers=2) as executor:
        discovered = executor.submit(discovery.discover_installed_slices)
        try:
            assert reading.wait(5)
            renamed = executor.submit(rename_source)
            assert attempted.wait(5)
            with pytest.raises(TimeoutError):
                renamed.result(timeout=0.1)
        finally:
            release.set()
        assert [manifest.key for manifest in discovered.result(timeout=5)] == ["source/demo-slice"]
        renamed.result(timeout=5)

    assert [manifest.key for manifest in discovery.discover_installed_slices()] == ["renamed/demo-slice"]
