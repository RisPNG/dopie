from __future__ import annotations

from typing import Any

from dopie.context import ApplicationContext
from dopie.models import SourceDefinition


class PreferencesBackend:
    def __init__(self, context: ApplicationContext):
        self.context = context

    def load_preferences(self) -> dict[str, Any]:
        return self.context.settings.load()

    def save_preferences(self, preferences: dict[str, Any]) -> None:
        current = self.context.settings.load()
        current.update(preferences)
        self.context.settings.save(current)

    def configure_application_updates(self, source: SourceDefinition, token: str | None) -> None:
        if token:
            self.context.vault.store_source_credential("application:update", token)
            source = SourceDefinition(
                id=source.id,
                name=source.name,
                repository_url=source.repository_url,
                reference=source.reference,
                index=source.index,
                credential="application:update",
                enabled=source.enabled,
            )
        current = self.context.shared_settings.load()
        current["application_update_source"] = {
            "id": source.id,
            "name": source.name,
            "repository_url": source.repository_url,
            "reference": source.reference,
            "index": source.index,
            "credential": source.credential,
        }
        self.context.shared_settings.save(current)
