from umbod.core.persistence import Database

from .errors import SettingsPermissionDenied, SettingsStorageUnavailable
from .models import (
    EffectiveFilesystemSettings,
    SettingsSource,
    SystemSettings,
    UpdatePortableConnectorSettings,
    UpdateSystemSettings,
)
from .ports import SettingsNotConfigured, SystemSettingsReader, SystemSettingsWriter
from .service import SystemSettingsService
from .store import DatabaseSystemSettingsStore

__all__ = [
    "EffectiveFilesystemSettings",
    "SettingsNotConfigured",
    "SettingsPermissionDenied",
    "SettingsSource",
    "SettingsStorageUnavailable",
    "SystemSettings",
    "SystemSettingsReader",
    "SystemSettingsService",
    "SystemSettingsWriter",
    "UpdatePortableConnectorSettings",
    "UpdateSystemSettings",
    "create_system_settings_service",
    "create_system_settings_service_with_defaults",
]


class _UnconfiguredDefaults:
    async def read(self) -> SettingsNotConfigured:
        return SettingsNotConfigured.UNSET


def create_system_settings_service(database: Database) -> SystemSettingsService:
    return create_system_settings_service_with_defaults(
        database,
        defaults=_UnconfiguredDefaults(),
    )


def create_system_settings_service_with_defaults(
    database: Database,
    *,
    defaults: SystemSettingsReader,
) -> SystemSettingsService:
    store = DatabaseSystemSettingsStore(database)
    return SystemSettingsService(overrides=store, writer=store, defaults=defaults)
