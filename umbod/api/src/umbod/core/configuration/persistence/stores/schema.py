from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    Field,
    KeyCodec,
    RowCodec,
    TextCodec,
    Fields,
    Table,
    TableIdentity,
)


class ConnectorConfigurationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    ciphertext: str
    updated_at: str


class ConnectorConfigurationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class EncryptedConnectorConfigurationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    ciphertext: str


class ConnectorConfigurationIdResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


CONNECTOR_CONFIGURATION_IDENTITY = TableIdentity("connector_configurations")
CONNECTOR_CONFIGURATION_CONNECTOR_ID = Field[ConnectorConfigurationRecord, str](
    CONNECTOR_CONFIGURATION_IDENTITY, "connector_id", TextCodec()
)
CONNECTOR_CONFIGURATION_CIPHERTEXT = Field[ConnectorConfigurationRecord, str](
    CONNECTOR_CONFIGURATION_IDENTITY, "ciphertext", TextCodec()
)
CONNECTOR_CONFIGURATION_UPDATED_AT = Field[ConnectorConfigurationRecord, str](
    CONNECTOR_CONFIGURATION_IDENTITY, "updated_at", TextCodec()
)
_CONNECTOR_CONFIGURATION_FIELDS = cast(
    tuple[Field[ConnectorConfigurationRecord, object], ...],
    (
        CONNECTOR_CONFIGURATION_CONNECTOR_ID,
        CONNECTOR_CONFIGURATION_CIPHERTEXT,
        CONNECTOR_CONFIGURATION_UPDATED_AT,
    ),
)
CONNECTOR_CONFIGURATION_TABLE = Table(
    CONNECTOR_CONFIGURATION_IDENTITY,
    RowCodec(ConnectorConfigurationRecord, _CONNECTOR_CONFIGURATION_FIELDS),
    KeyCodec(
        ConnectorConfigurationKey,
        cast(
            tuple[Field[ConnectorConfigurationRecord, object], ...],
            (CONNECTOR_CONFIGURATION_CONNECTOR_ID,),
        ),
    ),
)
ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION = Fields(
    EncryptedConnectorConfigurationResult,
    cast(
        tuple[Field[ConnectorConfigurationRecord, object], ...],
        (CONNECTOR_CONFIGURATION_CONNECTOR_ID, CONNECTOR_CONFIGURATION_CIPHERTEXT),
    ),
)
CONNECTOR_CONFIGURATION_ID_PROJECTION = Fields(
    ConnectorConfigurationIdResult,
    cast(
        tuple[Field[ConnectorConfigurationRecord, object], ...],
        (CONNECTOR_CONFIGURATION_CONNECTOR_ID,),
    ),
)
CONNECTOR_CONFIGURATIONS = CONNECTOR_CONFIGURATION_TABLE
