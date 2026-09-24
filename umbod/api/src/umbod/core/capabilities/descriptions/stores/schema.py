from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    ColumnCodec,
    ColumnType,
    Field,
    IntegerCodec,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)


class CapabilityDescriptionStorageCodec(ColumnCodec[str]):
    column_type: ClassVar[ColumnType] = ColumnType.NULLABLE_TEXT

    def encode(self, value: str) -> object:
        if not isinstance(value, str):
            raise TypeError("expected str")
        return value or None

    def decode(self, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise TypeError("expected stored text or null")
        return value


class CapabilityDescriptionOverrideRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    connector_kind: str
    state: str
    description: str
    revision: int


class CapabilityDescriptionOverrideKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY = TableIdentity(
    "connector_capability_description_overrides"
)
CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID = Field[CapabilityDescriptionOverrideRecord, str](
    CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY, "connector_id", TextCodec()
)
CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_KIND = Field[CapabilityDescriptionOverrideRecord, str](
    CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY, "connector_kind", TextCodec()
)
CAPABILITY_DESCRIPTION_OVERRIDE_STATE = Field[CapabilityDescriptionOverrideRecord, str](
    CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY, "state", TextCodec()
)
CAPABILITY_DESCRIPTION_OVERRIDE_DESCRIPTION = Field[CapabilityDescriptionOverrideRecord, str](
    CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY, "description", CapabilityDescriptionStorageCodec()
)
CAPABILITY_DESCRIPTION_OVERRIDE_REVISION = Field[CapabilityDescriptionOverrideRecord, int](
    CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY, "revision", IntegerCodec()
)
_FIELDS = cast(
    tuple[Field[CapabilityDescriptionOverrideRecord, object], ...],
    (
        CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID,
        CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_KIND,
        CAPABILITY_DESCRIPTION_OVERRIDE_STATE,
        CAPABILITY_DESCRIPTION_OVERRIDE_DESCRIPTION,
        CAPABILITY_DESCRIPTION_OVERRIDE_REVISION,
    ),
)
CAPABILITY_DESCRIPTION_OVERRIDE_TABLE = Table(
    CAPABILITY_DESCRIPTION_OVERRIDE_IDENTITY,
    RowCodec(CapabilityDescriptionOverrideRecord, _FIELDS),
    KeyCodec(
        CapabilityDescriptionOverrideKey,
        cast(
            tuple[Field[CapabilityDescriptionOverrideRecord, object], ...],
            (CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID,),
        ),
    ),
)
CAPABILITY_DESCRIPTION_OVERRIDES = CAPABILITY_DESCRIPTION_OVERRIDE_TABLE
