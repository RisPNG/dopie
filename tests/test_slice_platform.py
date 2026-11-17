from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest

from dopie.models import CatalogSlice, SliceManifest
from dopie.shared_folder import shared_folder_transaction
from dopie.slices.compatibility import evaluate_slice_compatibility
from dopie.slices.discovery import SliceDiscovery
from dopie.slices.installer import SliceInstaller
from dopie.slices.worker import prepare_slice_assets
from dopie.workspace.backend import SliceEnvironmentManager


def test_standard_slice_without_dependencies_needs_no_environment(tmp_path):
    slice_root = tmp_path / "slice"
    slice_root.mkdir()
    manifest_path = slice_root / "slice.toml"
    manifest_path.write_text(
        'id="safe"\nname="Safe"\nversion="1.0.0"\ndescription="Safe"\ninterface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    manifest = SliceManifest.load(manifest_path)

    plan = SliceEnvironmentManager(tmp_path / "environments").prepare_slice_environment(manifest)

    assert plan.packages is None
    assert plan.commands == ()
    assert plan.staging is None


def test_slice_dependencies_install_once_into_a_shared_package_folder(tmp_path):
    for slice_id in ("first", "second"):
        slice_root = tmp_path / slice_id
        slice_root.mkdir()
        slice_root.joinpath("slice.toml").write_text(
            f'id="{slice_id}"\nname="Safe"\nversion="1.0.0"\ndescription="Safe"\ninterface="standard"\n'
            'operation="backend:run"',
            encoding="utf-8",
        )
        slice_root.joinpath("requirements.lock").write_text("openpyxl==3.1.5 --hash=sha256:0\n", encoding="utf-8")
    manager = SliceEnvironmentManager(tmp_path / "environments")

    first = manager.prepare_slice_environment(SliceManifest.load(tmp_path / "first" / "slice.toml"))
    second = manager.prepare_slice_environment(SliceManifest.load(tmp_path / "second" / "slice.toml"))

    assert first.packages == second.packages
    assert first.packages.parent == tmp_path / "environments"
    assert first.staging.parent == first.packages.parent
    assert first.staging.name.startswith(f".{first.packages.name}-")
    command = first.commands[0]
    assert command[:5] == (sys.executable, "-I", "-m", "pip", "install")
    assert "--no-cache-dir" in command
    assert "--require-hashes" in command
    assert command[command.index("--target") + 1] == str(first.staging)
    first.staging.mkdir()
    first.staging.rename(first.packages)
    assert manager.prepare_slice_environment(SliceManifest.load(tmp_path / "first" / "slice.toml")).commands == ()


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


@pytest.mark.parametrize("installed", [False, True], ids=["source", "installed"])
def test_standard_slice_worker_imports_sibling_modules(tmp_path, installed):
    slice_root = tmp_path / "source" / "tool"
    slice_root.mkdir(parents=True)
    slice_root.joinpath("slice.toml").write_text(
        'id="tool"\nname="Tool"\nversion="0.1.0"\ndescription="Tool"\n'
        'interface="standard"\noperation="backend:run"',
        encoding="utf-8",
    )
    slice_root.joinpath("backend.py").write_text(
        "from . import processor\n\n"
        "def run(inputs, progress, log):\n"
        "    progress(50, 'Processor loaded')\n"
        "    log('Running tool')\n"
        "    return {'answer': processor.ANSWER, 'name': inputs['name']}\n",
        encoding="utf-8",
    )
    slice_root.joinpath("processor.py").write_text("ANSWER = 42\n", encoding="utf-8")
    if installed:
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            for path in slice_root.iterdir():
                bundle.write(path, f"tool/{path.name}")
        payload = archive.getvalue()
        item = CatalogSlice(
            "tool", "Tool", "0.1.0", "Tool", "Other", "DoPie", "MIT",
            "https://example.test/tool-0.1.0.zip", hashlib.sha256(payload).hexdigest(), "source",
        )
        installed_root = tmp_path / "installed"
        SliceInstaller(installed_root).install_slice(item, payload)
        [manifest] = SliceDiscovery(tmp_path / "bundled", installed_root).discover_installed_slices()
        assert manifest.path == installed_root / "sources" / "source" / "tool" / "versions" / "0.1.0"
    else:
        manifest = SliceManifest.load(slice_root / "slice.toml")
    worker = Path(__file__).parents[1] / "application" / "base" / "src" / "dopie" / "slices" / "worker.py"

    completed = subprocess.run(
        [sys.executable, "-I", str(worker), str(manifest.path), manifest.operation, ""],
        input=json.dumps({"name": "Ada"}),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert [json.loads(line) for line in completed.stdout.splitlines()] == [
        {"type": "progress", "value": 50, "message": "Processor loaded"},
        {"type": "log", "message": "Running tool"},
        {"type": "result", "value": {"answer": 42, "name": "Ada"}},
    ]


def test_installer_keeps_versions_and_can_roll_back(tmp_path):
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
    installer = SliceInstaller(tmp_path / "installed")
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
        installer.install_slice(item, payload)

    installer.activate_slice_version("tool", "1.0.0", "source")

    state_path = tmp_path / "installed" / "sources" / "source" / "tool" / "current.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["version"] == "1.0.0"
    assert installer.installed_versions("tool", "source") == ["1.0.0", "2.0.0"]


def test_same_id_from_two_sources_installs_updates_and_uninstalls_independently(tmp_path):
    payloads = {}
    for source_id in ("maintained", "community"):
        for version in ("1.0.0", "2.0.0"):
            archive = BytesIO()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "slice/slice.toml",
                    f'id="tool"\nname="Tool"\nversion="{version}"\ndescription="Tool"\n'
                    'interface="standard"\noperation="backend:run"',
                )
                bundle.writestr("slice/backend.py", f"PUBLISHER = '{source_id}'\nVERSION = '{version}'\n")
            payloads[f"https://example.test/{source_id}/{version}.zip"] = archive.getvalue()
    installed = tmp_path / "installed"
    installer = SliceInstaller(installed)
    for source_id, versions in (("maintained", ("1.0.0", "2.0.0")), ("community", ("1.0.0",))):
        for version in versions:
            url = f"https://example.test/{source_id}/{version}.zip"
            item = CatalogSlice(
                "tool", "Tool", version, "Tool", "Other", source_id, "MIT", url,
                hashlib.sha256(payloads[url]).hexdigest(), source_id,
            )
            installer.install_slice(item, payloads[url])

    assert installer.installed_versions("tool", "maintained") == ["1.0.0", "2.0.0"]
    assert installer.installed_versions("tool", "community") == ["1.0.0"]
    maintained = installed / "sources" / "maintained" / "tool"
    community = installed / "sources" / "community" / "tool"
    assert json.loads(maintained.joinpath("current.json").read_text())["version"] == "2.0.0"
    assert json.loads(community.joinpath("current.json").read_text())["version"] == "1.0.0"
    community_payload = community.joinpath("versions", "1.0.0", "backend.py").read_bytes()

    installer.activate_slice_version("tool", "1.0.0", "maintained")

    assert json.loads(maintained.joinpath("current.json").read_text())["version"] == "1.0.0"
    assert community.joinpath("versions", "1.0.0", "backend.py").read_bytes() == community_payload

    installer.uninstall_slice("tool", "maintained")

    assert installer.installed_versions("tool", "maintained") == []
    assert installer.installed_versions("tool", "community") == ["1.0.0"]
    assert community.joinpath("versions", "1.0.0", "backend.py").read_bytes() == community_payload


def test_source_less_managed_slice_keeps_rollback_and_uninstall_support(tmp_path):
    installed = tmp_path / "installed"
    root = installed / "local"
    for version in ("1.0.0", "2.0.0"):
        package = root / "versions" / version
        package.mkdir(parents=True)
        package.joinpath("slice.toml").write_text(
            f'id="local"\nname="Local"\nversion="{version}"\ndescription="Local"\n'
            'interface="standard"\noperation="backend:run"', encoding="utf-8"
        )
    root.joinpath("current.json").write_text('{"version": "2.0.0"}', encoding="utf-8")
    sourced = installed / "sources" / "local" / "tool"
    sourced_version = sourced / "versions" / "1.0.0"
    sourced_version.mkdir(parents=True)
    sourced_version.joinpath("slice.toml").write_text(
        'id="tool"\nname="Tool"\nversion="1.0.0"\ndescription="Tool"\n'
        'interface="standard"\noperation="backend:run"', encoding="utf-8"
    )
    sourced.joinpath("current.json").write_text(
        '{"version": "1.0.0", "source_id": "local"}', encoding="utf-8"
    )
    installer = SliceInstaller(installed)
    root = installed / "local" / "local"

    installer.activate_slice_version("local", "1.0.0")

    assert installer.installed_versions("local") == ["1.0.0", "2.0.0"]
    assert json.loads(root.joinpath("current.json").read_text())["version"] == "1.0.0"

    installer.uninstall_slice("local")

    assert not root.exists()
    assert installer.installed_versions("tool", "local") == ["1.0.0"]
    assert json.loads(sourced.joinpath("current.json").read_text())["version"] == "1.0.0"


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


def test_installer_rejects_catalog_identity_mismatch(tmp_path):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "slice/slice.toml",
            'id="different"\nname="Tool"\nversion="1.0.0"\ndescription="Tool"\ninterface="standard"\noperation="backend:run"',
        )
    payload = archive.getvalue()
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
        SliceInstaller(tmp_path / "installed").install_slice(item, payload)


@pytest.mark.parametrize("operation", ["install", "rollback", "versions", "uninstall"])
def test_installer_operations_wait_for_the_shared_installation_lock(tmp_path, operation):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "slice/slice.toml",
            'id="tool"\nname="Tool"\nversion="1.0.0"\ndescription="Tool"\n'
            'interface="standard"\noperation="backend:run"',
        )
    payload = archive.getvalue()
    item = CatalogSlice(
        "tool", "Tool", "1.0.0", "Tool", "Other", "Publisher", "MIT", "https://example.test/tool.zip",
        hashlib.sha256(payload).hexdigest(), "source",
    )
    installed = tmp_path / "installed"
    installer = SliceInstaller(installed)
    installer.install_slice(item, payload)
    attempted = Event()

    def perform_operation():
        attempted.set()
        if operation == "install":
            return installer.install_slice(item, payload)
        if operation == "rollback":
            return installer.activate_slice_version("tool", "1.0.0", "source")
        if operation == "versions":
            return installer.installed_versions("tool", "source")
        return installer.uninstall_slice("tool", "source")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with shared_folder_transaction(installed / ".configuration.lock"):
            result = executor.submit(perform_operation)
            assert attempted.wait(5)
            with pytest.raises(TimeoutError):
                result.result(timeout=0.1)
        result.result(timeout=5)
