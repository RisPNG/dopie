from __future__ import annotations

import json

import pytest

from dopie.models import SourceDefinition
from dopie.storage import DEFAULT_SHARED_SETTINGS, SettingsStore, SourceStore


def test_settings_store_uses_atomic_json_file(tmp_path):
    store = SettingsStore(tmp_path / "preferences.json")

    store.save({"include_available_in_library": True})

    assert store.load()["include_available_in_library"] is True
    assert "application_update_source" not in store.load()
    assert SettingsStore(store.path, DEFAULT_SHARED_SETTINGS).load()["application_update_source"]["repository_url"] == (
        "https://github.com/RisPNG/dopie"
    )
    assert not list(tmp_path.glob("*.tmp"))


def test_source_store_preserves_source_configuration(tmp_path):
    store = SourceStore(tmp_path / "sources.json")
    source = SourceDefinition(
        id="private",
        name="Private",
        repository_url="https://git.example.test/automation/slices",
        credential="source:private",
    )

    store.save([source])

    assert store.load() == [source]
    assert "source:private" in store.path.read_text(encoding="utf-8")
    assert '"repository_url"' in store.path.read_text(encoding="utf-8")
    assert '"provider"' not in store.path.read_text(encoding="utf-8")


def test_source_id_must_be_a_safe_stable_slug():
    with pytest.raises(ValueError, match="lowercase slug"):
        SourceDefinition("../private", "Private", "https://github.com/owner/repository")


def test_legacy_source_fields_migrate_to_repository_url():
    source = SourceDefinition.from_dict(
        {
            "id": "legacy",
            "name": "Legacy",
            "provider": "forgejo",
            "base_url": "https://code.example.test",
            "repository": "team/slices",
        }
    )

    assert source.repository_url == "https://code.example.test/team/slices"


def test_shared_settings_keep_the_folders_other_preferences(tmp_path):
    path = tmp_path / "preferences.json"
    custom = {
        "id": "dopie-application",
        "name": "DoPie Application",
        "repository_url": "https://git.example.test/team/dopie",
        "reference": "main",
        "index": "index.json",
        "credential": None,
    }
    path.write_text(json.dumps({"theme": "dark", "application_update_source": custom}), encoding="utf-8")
    shared_settings = SettingsStore(path, DEFAULT_SHARED_SETTINGS)

    assert shared_settings.load()["application_update_source"] == custom
    shared_preferences = shared_settings.load()
    shared_preferences["application_update_source"] = {**custom, "reference": "develop"}
    shared_settings.save(shared_preferences)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["theme"] == "dark"
    assert stored["application_update_source"]["reference"] == "develop"


def test_stores_do_not_collide_with_another_users_temporary_files(tmp_path):
    tmp_path.joinpath("sources.tmp").mkdir()
    tmp_path.joinpath("preferences.tmp").mkdir()
    source = SourceDefinition("public", "Public", "https://github.com/owner/public")

    SourceStore(tmp_path / "sources.json").save([source])
    SettingsStore(tmp_path / "preferences.json").save({"theme": "light"})

    assert SourceStore(tmp_path / "sources.json").load() == [source]
    assert SettingsStore(tmp_path / "preferences.json").load()["theme"] == "light"
    assert not list(tmp_path.glob("*.*.tmp"))
