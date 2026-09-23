from __future__ import annotations

import json
import zipfile

import pytest

from dopie.paths import resolve_app_paths
from dopie.security.vault import VaultStore
from dopie.sources.profile import PortableProfileService


@pytest.mark.parametrize("password", [None, "", "transfer password"])
def test_portable_profile_moves_encrypted_sources_without_installed_slices(tmp_path, monkeypatch, password):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    monkeypatch.setenv("DOPIE_ROOT", str(source_root))
    source_paths = resolve_app_paths()
    source_paths.sources.write_text(
        '[{"id":"private","name":"Private","repository_url":"https://github.com/owner/private",'
        '"credential":"source:private"}]',
        encoding="utf-8",
    )
    source_vault = VaultStore(source_paths.vault, source_paths.vault_key)
    source_vault.seal({"credentials": {"source:private": "token-value"}})
    installed = source_paths.installed_slices / "tool" / "versions" / "1.0.0"
    installed.mkdir(parents=True)
    installed.joinpath("slice.toml").write_text("installed", encoding="utf-8")
    profile = tmp_path / "portable.dopie-profile"
    PortableProfileService(source_paths).export_portable_profile(profile, password=password)

    monkeypatch.setenv("DOPIE_ROOT", str(destination_root))
    destination_paths = resolve_app_paths()
    service = PortableProfileService(destination_paths)
    assert service.profile_requires_password(profile) == bool(password)
    service.import_portable_profile(profile, password)

    assert VaultStore(destination_paths.vault, destination_paths.vault_key).unlock() == {
        "credentials": {"source:private": "token-value"}
    }
    assert not (destination_paths.installed_slices / "tool" / "versions" / "1.0.0").exists()
    assert destination_paths.vault_key.read_bytes() != source_paths.vault_key.read_bytes()


def test_existing_private_profile_still_requires_password(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPIE_ROOT", str(tmp_path))
    paths = resolve_app_paths()
    vault = VaultStore(paths.vault, paths.vault_key)
    secrets = {"credentials": {"source:private": "private-token"}}
    vault.seal(secrets)
    profile = tmp_path / "existing.dopie-profile"
    with zipfile.ZipFile(profile, "w") as archive:
        archive.writestr("profile.json", json.dumps({
            "format": "dopie-portable-profile", "version": 2, "private_sources": True,
        }))
        archive.writestr("data/source-vault.dopie", vault.export_for_transfer("password"))
    service = PortableProfileService(paths)

    assert service.profile_requires_password(profile)
    with pytest.raises(ValueError, match="transfer password is required"):
        service.import_portable_profile(profile)
    service.import_portable_profile(profile, "password")
    assert vault.unlock() == secrets


def test_portable_copy_contains_launchers_profile_and_no_local_state(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("README.md", "LICENSE", "start-dopie.sh"):
        root.joinpath(name).write_text(name, encoding="utf-8")
    base = root / "application" / "base"
    base.mkdir(parents=True)
    for name in ("pyproject.toml", "requirements.lock"):
        base.joinpath(name).write_text(name, encoding="utf-8")
    root.joinpath("Start DoPie.vbs").write_text("launcher", encoding="utf-8")
    bootstrap = root / "bootstrap"
    bootstrap.mkdir()
    bootstrap.joinpath("bootstrap.py").write_text("bootstrap", encoding="utf-8")
    bootstrap.joinpath("Start DoPie.ps1").write_text("powershell", encoding="utf-8")
    runtime = root / "runtime" / "linux"
    runtime.mkdir(parents=True)
    runtime.joinpath("python").write_text("runtime", encoding="utf-8")
    monkeypatch.setenv("DOPIE_ROOT", str(root))
    paths = resolve_app_paths()
    paths.sources.write_text("[]", encoding="utf-8")
    paths.data.joinpath("private-state").write_text("private", encoding="utf-8")
    for target_platform in ("linux", "windows", "both"):
        destination = tmp_path / f"DoPie-portable-{target_platform}.zip"
        PortableProfileService(paths).export_portable_copy(destination, target_platform)

        with zipfile.ZipFile(destination) as archive:
            names = set(archive.namelist())
        assert ("DoPie/start-dopie.sh" in names) == (target_platform in ("linux", "both"))
        assert ("DoPie/Start DoPie.vbs" in names) == (target_platform in ("windows", "both"))
        assert ("DoPie/bootstrap/Start DoPie.ps1" in names) == (
            target_platform in ("windows", "both")
        )
        assert "DoPie/bootstrap/bootstrap.py" in names
        assert "DoPie/provisioning/DoPie.dopie-profile" in names
        assert "DoPie/application/base/pyproject.toml" in names
        assert "DoPie/application/base/requirements.lock" in names
        assert "DoPie/README.md" not in names
        assert "DoPie/LICENSE" not in names
        assert "DoPie/pyproject.toml" not in names
        assert "DoPie/requirements.lock" not in names
        assert "DoPie/portable.toml" not in names
        assert all(not name.startswith("DoPie/runtime/") for name in names)
        assert all("private-state" not in name for name in names)
