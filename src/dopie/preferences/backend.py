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

    def configure_application_updates(
        self,
        source: SourceDefinition,
        token: str | None,
        vault_password: str | None,
        include_available: bool,
        check_updates: bool,
    ) -> None:
        if token:
            if self.context.vault.secrets is None and not vault_password:
                raise ValueError("The Source vault password is required for a private update Source")
            if self.context.paths.vault.exists() and self.context.vault.secrets is None:
                self.context.vault.unlock_private_sources(vault_password)
            elif not self.context.paths.vault.exists():
                self.context.vault.create_private_source_vault(vault_password)
            self.context.vault.store_source_credential("application:update", token)
            source = SourceDefinition(
                id=source.id,
                name=source.name,
                provider=source.provider,
                repository=source.repository,
                reference=source.reference,
                index=source.index,
                base_url=source.base_url,
                credential="application:update",
                public_key=source.public_key,
                enabled=source.enabled,
            )
        current = self.context.settings.load()
        current.update(
            {
                "include_available_in_library": include_available,
                "check_updates_on_launch": check_updates,
                "application_update_source": {
                    "id": source.id,
                    "name": source.name,
                    "provider": source.provider,
                    "base_url": source.base_url,
                    "repository": source.repository,
                    "reference": source.reference,
                    "index": source.index,
                    "credential": source.credential,
                    "public_key": source.public_key,
                },
            }
        )
        self.context.settings.save(current)
