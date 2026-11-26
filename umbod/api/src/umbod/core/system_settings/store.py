from typing import Final

from umbod.core.persistence import (
    AllFields,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Query,
    ReadSession,
    TransactionMode,
    Unordered,
    UpsertCommand,
)

from .errors import SettingsStorageUnavailable
from .models import SystemSettings, UpdateSystemSettings
from .ports import SettingsNotConfigured
from .schema import (
    SYSTEM_SETTINGS_KEY,
    SYSTEM_SETTINGS_TABLE,
    SystemSettingsKey,
    SystemSettingsRow,
)

_SINGLETON: Final[int] = 1


async def _read_settings_row(session: ReadSession) -> SystemSettingsRow | None:
    return await session.find_one(
        SYSTEM_SETTINGS_TABLE,
        Query(Equals(SYSTEM_SETTINGS_KEY, _SINGLETON), AllFields(), Unordered()),
    )


async def _save_settings(session: DatabaseSession, settings: SystemSettings) -> None:
    await session.upsert(
        SYSTEM_SETTINGS_TABLE,
        UpsertCommand(
            key=SystemSettingsKey(singleton=_SINGLETON),
            row=SystemSettingsRow(singleton=_SINGLETON, settings=settings),
        ),
    )


class DatabaseSystemSettingsStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def read(self) -> SystemSettings | SettingsNotConfigured:
        try:
            async with self._database.read_session() as session:
                row = await _read_settings_row(session)
                if (
                    row is None
                    or "require_mcp_file_deletion_approval"
                    not in row.settings.model_fields_set
                ):
                    return SettingsNotConfigured.UNSET
                return row.settings
        except Exception:
            raise SettingsStorageUnavailable() from None

    async def update(self, command: UpdateSystemSettings) -> SystemSettings:
        try:
            async with self._database.session(
                mode=TransactionMode.SERIALIZED_WRITE
            ) as session:
                row = await _read_settings_row(session)
                overrides = {} if row is None else row.settings.model_dump(exclude_unset=True)
                overrides.update(command.model_dump(exclude_unset=True))
                updated = SystemSettings.model_validate(overrides)
                await _save_settings(session, updated)
        except Exception:
            raise SettingsStorageUnavailable() from None
        return updated

    async def reset_mcp_file_deletion_approval(self) -> None:
        try:
            async with self._database.session(
                mode=TransactionMode.SERIALIZED_WRITE
            ) as session:
                row = await _read_settings_row(session)
                if row is None:
                    return
                remaining = row.settings.model_dump(
                    exclude_unset=True,
                    exclude={"require_mcp_file_deletion_approval"},
                )
                if remaining:
                    await _save_settings(session, SystemSettings.model_validate(remaining))
                    return
                await session.delete(
                    SYSTEM_SETTINGS_TABLE,
                    DeleteQuery(Equals(SYSTEM_SETTINGS_KEY, _SINGLETON)),
                )
        except Exception:
            raise SettingsStorageUnavailable() from None
