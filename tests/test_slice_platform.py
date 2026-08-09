from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO

import pytest

from dopie.models import CatalogSlice, SliceManifest, SourceDefinition
from dopie.slices.compatibility import evaluate_slice_compatibility
from dopie.slices.installer import SliceInstaller
from dopie.slices.worker import prepare_slice_assets
from dopie.sources.remote import RemoteRepositoryClient
from dopie.workspace.backend import SliceEnvironmentManager


def test_standard_slice_gets_an_isolated_environment_without_dependencies(tmp_path):
    slice_root = tmp_path / "slice"
    slice_root.mkdir()
    manifest_path = slice_root / "slice.toml"
    manifest_path.write_text(
        'id="safe"\nname="Safe"\nversion="1.0.0"\ndescription="Safe"\ninterface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    manifest = SliceManifest.load(manifest_path)

    plan = SliceEnvironmentManager(tmp_path / "environments").prepare_slice_environment(manifest)

    assert len(plan.commands) == 1
    assert plan.commands[0][1:3] == ("-m", "venv")
    assert plan.python != manifest.path


def test_slice_dependency_install_does_not_use_the_user_cache(tmp_path):
    slice_root = tmp_path / "slice"
    slice_root.mkdir()
    manifest_path = slice_root / "slice.toml"
    manifest_path.write_text(
        'id="safe"\nname="Safe"\nversion="1.0.0"\ndescription="Safe"\ninterface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    slice_root.joinpath("requirements.lock").write_text("", encoding="utf-8")

    plan = SliceEnvironmentManager(tmp_path / "environments").prepare_slice_environment(
        SliceManifest.load(manifest_path)
    )

    assert "--no-cache-dir" in plan.commands[1]


def test_slice_assets_are_downloaded_and_verified(tmp_path):
    payload = b"trusted asset"
    source = tmp_path / "source.bin"
    source.write_bytes(payload)

    resolved = prepare_slice_assets(
        tmp_path / "assets",
        [{"id": "model.bin", "url": source.as_uri(), "sha256": hashlib.sha256(payload).hexdigest()}],
    )

    assert (tmp_path / "assets" / "model.bin").read_bytes() == payload
    assert resolved["model.bin"].endswith("model.bin")


def test_installer_keeps_versions_and_can_roll_back(tmp_path, monkeypatch):
    def package(version: str) -> bytes:
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(
                "slice/slice.toml",
                f'id="tool"\nname="Tool"\nversion="{version}"\ndescription="Tool"\ninterface="standard"\noperation="backend:run"',
            )
            bundle.writestr("slice/backend.py", "def run(inputs, progress, log): return inputs\n")
        return archive.getvalue()

    packages = {version: package(version) for version in ("1.0.0", "2.0.0")}
    monkeypatch.setattr(
        RemoteRepositoryClient,
        "download_artifact",
        lambda self, url: packages[url.rsplit("/", 1)[-1]],
    )
    installer = SliceInstaller(tmp_path / "installed")
    source = SourceDefinition("source", "Source", "https://github.com/owner/repository")
    for version in packages:
        payload = packages[version]
        item = CatalogSlice(
            "tool",
            "Tool",
            version,
            "Tool",
            "Other",
            "DoPie",
            "MIT",
            f"https://example.test/{version}",
            hashlib.sha256(payload).hexdigest(),
            "source",
        )
        installer.install_slice(item, source)

    installer.activate_slice_version("tool", "1.0.0")

    state = json.loads((tmp_path / "installed" / "tool" / "current.json").read_text(encoding="utf-8"))
    assert state["version"] == "1.0.0"
    assert installer.installed_versions("tool") == ["1.0.0", "2.0.0"]


def test_incompatible_slice_is_explained():
    item = CatalogSlice(
        "future",
        "Future",
        "1.0.0",
        "Future",
        "Other",
        "DoPie",
        "MIT",
        "https://example.test/future.zip",
        "abc",
        "source",
        api_version=99,
    )

    compatibility = evaluate_slice_compatibility(item)

    assert not compatibility.compatible
    assert "Pie API" in compatibility.reason


def test_installer_rejects_catalog_identity_mismatch(tmp_path, monkeypatch):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "slice/slice.toml",
            'id="different"\nname="Tool"\nversion="1.0.0"\ndescription="Tool"\ninterface="standard"\noperation="backend:run"',
        )
    payload = archive.getvalue()
    monkeypatch.setattr(RemoteRepositoryClient, "download_artifact", lambda self, url: payload)
    item = CatalogSlice(
        "tool",
        "Tool",
        "1.0.0",
        "Tool",
        "Other",
        "DoPie",
        "MIT",
        "https://example.test/tool.zip",
        hashlib.sha256(payload).hexdigest(),
        "source",
    )

    with pytest.raises(ValueError, match="identity"):
        SliceInstaller(tmp_path / "installed").install_slice(
            item, SourceDefinition("source", "Source", "https://github.com/owner/repository")
        )
