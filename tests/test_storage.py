from __future__ import annotations

from dopie.models import SourceDefinition
from dopie.storage import SettingsStore, SourceStore


def test_settings_store_uses_atomic_json_file(tmp_path):
    store = SettingsStore(tmp_path / "preferences.json")

    store.save({"include_available_in_library": True})

    assert store.load() == {"include_available_in_library": True}
    assert not (tmp_path / "preferences.tmp").exists()


def test_source_store_preserves_source_configuration(tmp_path):
    store = SourceStore(tmp_path / "sources.json")
    source = SourceDefinition(
        id="private",
        name="Private",
        provider="forgejo",
        base_url="https://git.example.test",
        repository="automation/slices",
        credential="source:private",
    )

    store.save([source])

    assert store.load() == [source]
    assert "source:private" in store.path.read_text(encoding="utf-8")
