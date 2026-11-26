from typing import cast

from umbod.core.persistence import (
    AllFields,
    Database,
    Field,
    IntegerCodec,
    JsonValueCodec,
    KeyCodec,
    NoFilter,
    Query,
    RowCodec,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from umbod.core.system_settings.schema import (
    SYSTEM_SETTINGS_IDENTITY,
    SYSTEM_SETTINGS_VALUE,
    SystemSettingsKey,
)


class _RawSettingsRow(SystemSettingsKey):
    settings: object


_RAW_KEY = Field[_RawSettingsRow, int](
    SYSTEM_SETTINGS_IDENTITY, "singleton", IntegerCodec()
)
_RAW_VALUE = Field[_RawSettingsRow, object](
    SYSTEM_SETTINGS_IDENTITY, SYSTEM_SETTINGS_VALUE.name, JsonValueCodec()
)
_RAW_TABLE = Table(
    SYSTEM_SETTINGS_IDENTITY,
    RowCodec(
        _RawSettingsRow, (cast(Field[_RawSettingsRow, object], _RAW_KEY), _RAW_VALUE)
    ),
    KeyCodec(SystemSettingsKey, (cast(Field[_RawSettingsRow, object], _RAW_KEY),)),
)


async def save_raw_settings(database: Database, payload: object) -> None:
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(
            _RAW_TABLE,
            UpsertCommand(
                key=SystemSettingsKey(singleton=1),
                row=_RawSettingsRow(singleton=1, settings=payload),
            ),
        )


async def read_raw_settings(database: Database) -> list[object]:
    async with database.read_session() as session:
        rows = await session.find_many(
            _RAW_TABLE, Query(NoFilter(), AllFields(), Unordered())
        )
    return [row.settings for row in rows]
