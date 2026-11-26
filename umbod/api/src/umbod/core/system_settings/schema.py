from typing import cast

from pydantic import BaseModel

from umbod.core.persistence import (
    Field,
    IntegerCodec,
    JsonValueCodec,
    KeyCodec,
    PydanticJsonCodec,
    RowCodec,
    Table,
    TableIdentity,
)

from .models import SystemSettings


class SystemSettingsKey(BaseModel):
    singleton: int


class SystemSettingsRow(SystemSettingsKey):
    settings: SystemSettings


class SystemSettingsJsonCodec(PydanticJsonCodec[SystemSettings]):
    def encode(self, value: SystemSettings) -> object:
        sparse = value.model_dump(mode="json", exclude_unset=True)
        return JsonValueCodec[object]().encode(sparse)


SYSTEM_SETTINGS_IDENTITY = TableIdentity("system_settings")
SYSTEM_SETTINGS_KEY = Field[SystemSettingsRow, int](
    SYSTEM_SETTINGS_IDENTITY, "singleton", IntegerCodec()
)
SYSTEM_SETTINGS_VALUE = Field[SystemSettingsRow, SystemSettings](
    SYSTEM_SETTINGS_IDENTITY, "settings", SystemSettingsJsonCodec(SystemSettings)
)
SYSTEM_SETTINGS_TABLE = Table(
    SYSTEM_SETTINGS_IDENTITY,
    RowCodec(
        SystemSettingsRow,
        cast(
            tuple[Field[SystemSettingsRow, object], ...],
            (SYSTEM_SETTINGS_KEY, SYSTEM_SETTINGS_VALUE),
        ),
    ),
    KeyCodec(
        SystemSettingsKey,
        cast(tuple[Field[SystemSettingsRow, object], ...], (SYSTEM_SETTINGS_KEY,)),
    ),
)
