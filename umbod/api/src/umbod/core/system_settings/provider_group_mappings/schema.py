from typing import cast

from pydantic import BaseModel, ConfigDict, RootModel

from umbod.core.persistence import (
    Field,
    IntegerCodec,
    KeyCodec,
    PydanticJsonCodec,
    RowCodec,
    Table,
    TableIdentity,
)

from .models import ProviderGroupMappings


class StoredProviderGroupMappings(RootModel[ProviderGroupMappings]):
    model_config = ConfigDict(frozen=True)


class ProviderGroupMappingsKey(BaseModel):
    singleton: int


class ProviderGroupMappingsRow(ProviderGroupMappingsKey):
    settings: StoredProviderGroupMappings


MAPPINGS_IDENTITY = TableIdentity("provider_group_mapping_settings")
MAPPINGS_KEY = Field[ProviderGroupMappingsRow, int](
    MAPPINGS_IDENTITY, "singleton", IntegerCodec()
)
MAPPINGS_VALUE = Field[ProviderGroupMappingsRow, StoredProviderGroupMappings](
    MAPPINGS_IDENTITY, "settings", PydanticJsonCodec(StoredProviderGroupMappings)
)
PROVIDER_GROUP_MAPPINGS_TABLE = Table(
    MAPPINGS_IDENTITY,
    RowCodec(
        ProviderGroupMappingsRow,
        cast(
            tuple[Field[ProviderGroupMappingsRow, object], ...],
            (MAPPINGS_KEY, MAPPINGS_VALUE),
        ),
    ),
    KeyCodec(
        ProviderGroupMappingsKey,
        cast(tuple[Field[ProviderGroupMappingsRow, object], ...], (MAPPINGS_KEY,)),
    ),
)
