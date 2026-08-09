from __future__ import annotations

import pytest

from dopie.models import SourceDefinition
from dopie.storage import SettingsStore, SourceStore


def test_settings_store_uses_atomic_json_file(tmp_path):
    store = SettingsStore(tmp_path / "preferences.json")

    store.save({"include_available_in_library": True})

    assert store.load()["include_available_in_library"] is True
    assert store.load()["application_update_source"]["repository_url"] == "https://github.com/RisPNG/dopie"
    assert not (tmp_path / "preferences.tmp").exists()


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
