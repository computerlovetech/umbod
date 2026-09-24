from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    Field,
    JsonValueCodec,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)


class ConnectorDefinitionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: dict[str, object]
    public_path: str
    capability_description: str


class ConnectorDefinitionKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class ConnectorCredentialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: str


class ConnectorCredentialKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class ToolCatalogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    snapshot: dict[str, object]


class ToolCatalogKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class ConnectorHealthRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: dict[str, object]


class ConnectorHealthKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


CONNECTOR_DEFINITION_IDENTITY = TableIdentity("downstream_mcp_connector_definitions")
CONNECTOR_DEFINITION_CONNECTOR_ID = Field[ConnectorDefinitionRecord, str](
    CONNECTOR_DEFINITION_IDENTITY, "connector_id", TextCodec()
)
CONNECTOR_DEFINITION_DOCUMENT = Field[ConnectorDefinitionRecord, dict[str, object]](
    CONNECTOR_DEFINITION_IDENTITY, "document", JsonValueCodec()
)
CONNECTOR_DEFINITION_PUBLIC_PATH = Field[ConnectorDefinitionRecord, str](
    CONNECTOR_DEFINITION_IDENTITY, "public_path", TextCodec()
)
CONNECTOR_DEFINITION_CAPABILITY_DESCRIPTION = Field[ConnectorDefinitionRecord, str](
    CONNECTOR_DEFINITION_IDENTITY, "capability_description", TextCodec()
)
_CONNECTOR_DEFINITION_FIELDS = cast(
    tuple[Field[ConnectorDefinitionRecord, object], ...],
    (
        CONNECTOR_DEFINITION_CONNECTOR_ID,
        CONNECTOR_DEFINITION_DOCUMENT,
        CONNECTOR_DEFINITION_PUBLIC_PATH,
        CONNECTOR_DEFINITION_CAPABILITY_DESCRIPTION,
    ),
)
CONNECTOR_DEFINITION_TABLE = Table(
    CONNECTOR_DEFINITION_IDENTITY,
    RowCodec(ConnectorDefinitionRecord, _CONNECTOR_DEFINITION_FIELDS),
    KeyCodec(
        ConnectorDefinitionKey,
        cast(
            tuple[Field[ConnectorDefinitionRecord, object], ...],
            (CONNECTOR_DEFINITION_CONNECTOR_ID,),
        ),
    ),
)


CONNECTOR_CREDENTIAL_IDENTITY = TableIdentity("downstream_mcp_connector_credentials")
CONNECTOR_CREDENTIAL_CONNECTOR_ID = Field[ConnectorCredentialRecord, str](
    CONNECTOR_CREDENTIAL_IDENTITY, "connector_id", TextCodec()
)
CONNECTOR_CREDENTIAL_DOCUMENT = Field[ConnectorCredentialRecord, str](
    CONNECTOR_CREDENTIAL_IDENTITY, "document", TextCodec()
)
_CONNECTOR_CREDENTIAL_FIELDS = cast(
    tuple[Field[ConnectorCredentialRecord, object], ...],
    (CONNECTOR_CREDENTIAL_CONNECTOR_ID, CONNECTOR_CREDENTIAL_DOCUMENT),
)
CONNECTOR_CREDENTIAL_TABLE = Table(
    CONNECTOR_CREDENTIAL_IDENTITY,
    RowCodec(ConnectorCredentialRecord, _CONNECTOR_CREDENTIAL_FIELDS),
    KeyCodec(
        ConnectorCredentialKey,
        cast(
            tuple[Field[ConnectorCredentialRecord, object], ...],
            (CONNECTOR_CREDENTIAL_CONNECTOR_ID,),
        ),
    ),
)


TOOL_CATALOG_IDENTITY = TableIdentity("downstream_mcp_tool_catalogs")
TOOL_CATALOG_CONNECTOR_ID = Field[ToolCatalogRecord, str](
    TOOL_CATALOG_IDENTITY, "connector_id", TextCodec()
)
TOOL_CATALOG_SNAPSHOT = Field[ToolCatalogRecord, dict[str, object]](
    TOOL_CATALOG_IDENTITY, "snapshot", JsonValueCodec()
)
_TOOL_CATALOG_FIELDS = cast(
    tuple[Field[ToolCatalogRecord, object], ...],
    (TOOL_CATALOG_CONNECTOR_ID, TOOL_CATALOG_SNAPSHOT),
)
TOOL_CATALOG_TABLE = Table(
    TOOL_CATALOG_IDENTITY,
    RowCodec(ToolCatalogRecord, _TOOL_CATALOG_FIELDS),
    KeyCodec(
        ToolCatalogKey,
        cast(
            tuple[Field[ToolCatalogRecord, object], ...],
            (TOOL_CATALOG_CONNECTOR_ID,),
        ),
    ),
)


CONNECTOR_HEALTH_IDENTITY = TableIdentity("downstream_mcp_connector_health")
CONNECTOR_HEALTH_CONNECTOR_ID = Field[ConnectorHealthRecord, str](
    CONNECTOR_HEALTH_IDENTITY, "connector_id", TextCodec()
)
CONNECTOR_HEALTH_DOCUMENT = Field[ConnectorHealthRecord, dict[str, object]](
    CONNECTOR_HEALTH_IDENTITY, "document", JsonValueCodec()
)
_CONNECTOR_HEALTH_FIELDS = cast(
    tuple[Field[ConnectorHealthRecord, object], ...],
    (CONNECTOR_HEALTH_CONNECTOR_ID, CONNECTOR_HEALTH_DOCUMENT),
)
CONNECTOR_HEALTH_TABLE = Table(
    CONNECTOR_HEALTH_IDENTITY,
    RowCodec(ConnectorHealthRecord, _CONNECTOR_HEALTH_FIELDS),
    KeyCodec(
        ConnectorHealthKey,
        cast(
            tuple[Field[ConnectorHealthRecord, object], ...],
            (CONNECTOR_HEALTH_CONNECTOR_ID,),
        ),
    ),
)
