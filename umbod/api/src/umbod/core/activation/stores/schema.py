from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    Field,
    Fields,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)


class CapabilityActivationStateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: str
    connector_id: str
    capability_kind: str
    capability_key: str
    status: str
    updated_at: str


class CapabilityActivationStateKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: str
    connector_id: str
    capability_kind: str
    capability_key: str


class CapabilityActivationStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str


CAPABILITY_ACTIVATION_STATE_IDENTITY = TableIdentity("capability_activation_states")
CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND = Field[CapabilityActivationStateRecord, str](
    CAPABILITY_ACTIVATION_STATE_IDENTITY, "connector_kind", TextCodec()
)
CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID = Field[CapabilityActivationStateRecord, str](
    CAPABILITY_ACTIVATION_STATE_IDENTITY, "connector_id", TextCodec()
)
CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND = Field[CapabilityActivationStateRecord, str](
    CAPABILITY_ACTIVATION_STATE_IDENTITY, "capability_kind", TextCodec()
)
CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY = Field[CapabilityActivationStateRecord, str](
    CAPABILITY_ACTIVATION_STATE_IDENTITY, "capability_key", TextCodec()
)
CAPABILITY_ACTIVATION_STATE_STATUS = Field[CapabilityActivationStateRecord, str](
    CAPABILITY_ACTIVATION_STATE_IDENTITY, "status", TextCodec()
)
CAPABILITY_ACTIVATION_STATE_UPDATED_AT = Field[CapabilityActivationStateRecord, str](
    CAPABILITY_ACTIVATION_STATE_IDENTITY, "updated_at", TextCodec()
)
_CAPABILITY_ACTIVATION_STATE_FIELDS = cast(
    tuple[Field[CapabilityActivationStateRecord, object], ...],
    (
        CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
        CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
        CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
        CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
        CAPABILITY_ACTIVATION_STATE_STATUS,
        CAPABILITY_ACTIVATION_STATE_UPDATED_AT,
    ),
)
CAPABILITY_ACTIVATION_STATE_TABLE = Table(
    CAPABILITY_ACTIVATION_STATE_IDENTITY,
    RowCodec(CapabilityActivationStateRecord, _CAPABILITY_ACTIVATION_STATE_FIELDS),
    KeyCodec(
        CapabilityActivationStateKey,
        cast(
            tuple[Field[CapabilityActivationStateRecord, object], ...],
            (
                CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
                CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
                CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
                CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
            ),
        ),
    ),
)
CAPABILITY_ACTIVATION_STATUS_PROJECTION = Fields(
    CapabilityActivationStatusResult,
    cast(
        tuple[Field[CapabilityActivationStateRecord, object], ...],
        (CAPABILITY_ACTIVATION_STATE_STATUS,),
    ),
)
CAPABILITY_ACTIVATION_STATES = CAPABILITY_ACTIVATION_STATE_TABLE
