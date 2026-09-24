from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.connectors.openapi.models import OpenApiEndpointCapability, OpenApiMetadata
from umbod.core.persistence.query import (
    Field,
    JsonTupleCodec,
    JsonValueCodec,
    KeyCodec,
    PydanticJsonCodec,
    RowCodec,
    TextCodec,
    Fields,
    Table,
    TableIdentity,
)


class ConnectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: str


class ConnectorKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class ConnectorDocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document: str


class ConnectorListResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: str


CONNECTOR_IDENTITY = TableIdentity("openapi_connectors")
CONNECTOR_ID = Field[ConnectorRecord, str](CONNECTOR_IDENTITY, "connector_id", TextCodec())
CONNECTOR_DOCUMENT = Field[ConnectorRecord, str](CONNECTOR_IDENTITY, "document", TextCodec())
_CONNECTOR_FIELDS = cast(
    tuple[Field[ConnectorRecord, object], ...], (CONNECTOR_ID, CONNECTOR_DOCUMENT)
)
CONNECTOR_TABLE = Table(
    CONNECTOR_IDENTITY,
    RowCodec(ConnectorRecord, _CONNECTOR_FIELDS),
    KeyCodec(ConnectorKey, cast(tuple[Field[ConnectorRecord, object], ...], (CONNECTOR_ID,))),
)
CONNECTOR_DOCUMENT_PROJECTION = Fields(
    ConnectorDocumentResult,
    cast(tuple[Field[ConnectorRecord, object], ...], (CONNECTOR_DOCUMENT,)),
)
CONNECTOR_LIST_PROJECTION = Fields(
    ConnectorListResult,
    cast(tuple[Field[ConnectorRecord, object], ...], (CONNECTOR_ID, CONNECTOR_DOCUMENT)),
)
CONNECTORS = CONNECTOR_TABLE


class CurrentCatalogHeaderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    metadata: OpenApiMetadata
    server_candidates: tuple[str, ...]
    approved_hosts: tuple[str, ...]
    selected_server_url: str
    operation_ids: tuple[str, ...]
    imported_at: str


class CurrentCatalogHeaderKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class CurrentCatalogConnectorIdResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


CURRENT_CATALOG_HEADER_IDENTITY = TableIdentity("openapi_current_catalog_headers")
CURRENT_CATALOG_HEADER_CONNECTOR_ID = Field[CurrentCatalogHeaderRecord, str](
    CURRENT_CATALOG_HEADER_IDENTITY, "connector_id", TextCodec()
)
CURRENT_CATALOG_HEADER_CATALOG_ID = Field[CurrentCatalogHeaderRecord, str](
    CURRENT_CATALOG_HEADER_IDENTITY, "catalog_id", TextCodec()
)
CURRENT_CATALOG_HEADER_METADATA = Field[CurrentCatalogHeaderRecord, OpenApiMetadata](
    CURRENT_CATALOG_HEADER_IDENTITY, "metadata", PydanticJsonCodec(OpenApiMetadata)
)
CURRENT_CATALOG_HEADER_SERVER_CANDIDATES = Field[CurrentCatalogHeaderRecord, tuple[str, ...]](
    CURRENT_CATALOG_HEADER_IDENTITY, "server_candidates", JsonTupleCodec[str]()
)
CURRENT_CATALOG_HEADER_APPROVED_HOSTS = Field[CurrentCatalogHeaderRecord, tuple[str, ...]](
    CURRENT_CATALOG_HEADER_IDENTITY, "approved_hosts", JsonTupleCodec[str]()
)
CURRENT_CATALOG_HEADER_SELECTED_SERVER_URL = Field[CurrentCatalogHeaderRecord, str](
    CURRENT_CATALOG_HEADER_IDENTITY, "selected_server_url", TextCodec()
)
CURRENT_CATALOG_HEADER_OPERATION_IDS = Field[CurrentCatalogHeaderRecord, tuple[str, ...]](
    CURRENT_CATALOG_HEADER_IDENTITY, "operation_ids", JsonTupleCodec[str]()
)
CURRENT_CATALOG_HEADER_IMPORTED_AT = Field[CurrentCatalogHeaderRecord, str](
    CURRENT_CATALOG_HEADER_IDENTITY, "imported_at", TextCodec()
)
_CURRENT_CATALOG_HEADER_FIELDS = cast(
    tuple[Field[CurrentCatalogHeaderRecord, object], ...],
    (
        CURRENT_CATALOG_HEADER_CONNECTOR_ID,
        CURRENT_CATALOG_HEADER_CATALOG_ID,
        CURRENT_CATALOG_HEADER_METADATA,
        CURRENT_CATALOG_HEADER_SERVER_CANDIDATES,
        CURRENT_CATALOG_HEADER_APPROVED_HOSTS,
        CURRENT_CATALOG_HEADER_SELECTED_SERVER_URL,
        CURRENT_CATALOG_HEADER_OPERATION_IDS,
        CURRENT_CATALOG_HEADER_IMPORTED_AT,
    ),
)
CURRENT_CATALOG_HEADER_TABLE = Table(
    CURRENT_CATALOG_HEADER_IDENTITY,
    RowCodec(CurrentCatalogHeaderRecord, _CURRENT_CATALOG_HEADER_FIELDS),
    KeyCodec(
        CurrentCatalogHeaderKey,
        cast(
            tuple[Field[CurrentCatalogHeaderRecord, object], ...],
            (CURRENT_CATALOG_HEADER_CONNECTOR_ID,),
        ),
    ),
)
CURRENT_CATALOG_HEADER_ID_PROJECTION = Fields(
    CurrentCatalogConnectorIdResult,
    cast(
        tuple[Field[CurrentCatalogHeaderRecord, object], ...],
        (CURRENT_CATALOG_HEADER_CONNECTOR_ID,),
    ),
)
CURRENT_CATALOG_HEADERS = CURRENT_CATALOG_HEADER_TABLE


class CatalogSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    document: dict[str, object]


class CatalogSourceKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str


class CatalogSourceDocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document: dict[str, object]


CATALOG_SOURCE_IDENTITY = TableIdentity("openapi_catalog_sources")
CATALOG_SOURCE_CONNECTOR_ID = Field[CatalogSourceRecord, str](
    CATALOG_SOURCE_IDENTITY, "connector_id", TextCodec()
)
CATALOG_SOURCE_CATALOG_ID = Field[CatalogSourceRecord, str](
    CATALOG_SOURCE_IDENTITY, "catalog_id", TextCodec()
)
CATALOG_SOURCE_DOCUMENT = Field[CatalogSourceRecord, dict[str, object]](
    CATALOG_SOURCE_IDENTITY, "document", JsonValueCodec[dict[str, object]]()
)
_CATALOG_SOURCE_FIELDS = cast(
    tuple[Field[CatalogSourceRecord, object], ...],
    (CATALOG_SOURCE_CONNECTOR_ID, CATALOG_SOURCE_CATALOG_ID, CATALOG_SOURCE_DOCUMENT),
)
CATALOG_SOURCE_TABLE = Table(
    CATALOG_SOURCE_IDENTITY,
    RowCodec(CatalogSourceRecord, _CATALOG_SOURCE_FIELDS),
    KeyCodec(
        CatalogSourceKey,
        cast(
            tuple[Field[CatalogSourceRecord, object], ...],
            (CATALOG_SOURCE_CONNECTOR_ID, CATALOG_SOURCE_CATALOG_ID),
        ),
    ),
)
CATALOG_SOURCE_DOCUMENT_PROJECTION = Fields(
    CatalogSourceDocumentResult,
    cast(tuple[Field[CatalogSourceRecord, object], ...], (CATALOG_SOURCE_DOCUMENT,)),
)
CATALOG_SOURCES = CATALOG_SOURCE_TABLE


class CatalogOperationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    tags: tuple[str, ...]
    capability: OpenApiEndpointCapability


class CatalogOperationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    operation_id: str


class CatalogOperationSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    catalog_id: str
    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    tags: tuple[str, ...]


class CatalogOperationCapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: OpenApiEndpointCapability


CATALOG_OPERATION_IDENTITY = TableIdentity("openapi_catalog_operations")
CATALOG_OPERATION_CONNECTOR_ID = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "connector_id", TextCodec()
)
CATALOG_OPERATION_CATALOG_ID = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "catalog_id", TextCodec()
)
CATALOG_OPERATION_OPERATION_ID = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "operation_id", TextCodec()
)
CATALOG_OPERATION_METHOD = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "method", TextCodec()
)
CATALOG_OPERATION_PATH = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "path", TextCodec()
)
CATALOG_OPERATION_SUMMARY = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "summary", TextCodec()
)
CATALOG_OPERATION_DESCRIPTION = Field[CatalogOperationRecord, str](
    CATALOG_OPERATION_IDENTITY, "description", TextCodec()
)
CATALOG_OPERATION_TAGS = Field[CatalogOperationRecord, tuple[str, ...]](
    CATALOG_OPERATION_IDENTITY, "tags", JsonTupleCodec[str]()
)
CATALOG_OPERATION_CAPABILITY = Field[CatalogOperationRecord, OpenApiEndpointCapability](
    CATALOG_OPERATION_IDENTITY, "capability", PydanticJsonCodec(OpenApiEndpointCapability)
)
_CATALOG_OPERATION_FIELDS = cast(
    tuple[Field[CatalogOperationRecord, object], ...],
    (
        CATALOG_OPERATION_CONNECTOR_ID,
        CATALOG_OPERATION_CATALOG_ID,
        CATALOG_OPERATION_OPERATION_ID,
        CATALOG_OPERATION_METHOD,
        CATALOG_OPERATION_PATH,
        CATALOG_OPERATION_SUMMARY,
        CATALOG_OPERATION_DESCRIPTION,
        CATALOG_OPERATION_TAGS,
        CATALOG_OPERATION_CAPABILITY,
    ),
)
CATALOG_OPERATION_TABLE = Table(
    CATALOG_OPERATION_IDENTITY,
    RowCodec(CatalogOperationRecord, _CATALOG_OPERATION_FIELDS),
    KeyCodec(
        CatalogOperationKey,
        cast(
            tuple[Field[CatalogOperationRecord, object], ...],
            (
                CATALOG_OPERATION_CONNECTOR_ID,
                CATALOG_OPERATION_CATALOG_ID,
                CATALOG_OPERATION_OPERATION_ID,
            ),
        ),
    ),
)
CATALOG_OPERATION_SUMMARY_PROJECTION = Fields(
    CatalogOperationSummaryResult,
    cast(
        tuple[Field[CatalogOperationRecord, object], ...],
        (
            CATALOG_OPERATION_CONNECTOR_ID,
            CATALOG_OPERATION_CATALOG_ID,
            CATALOG_OPERATION_OPERATION_ID,
            CATALOG_OPERATION_METHOD,
            CATALOG_OPERATION_PATH,
            CATALOG_OPERATION_SUMMARY,
            CATALOG_OPERATION_DESCRIPTION,
            CATALOG_OPERATION_TAGS,
        ),
    ),
)
CATALOG_OPERATION_CAPABILITY_PROJECTION = Fields(
    CatalogOperationCapabilityResult,
    cast(tuple[Field[CatalogOperationRecord, object], ...], (CATALOG_OPERATION_CAPABILITY,)),
)
CATALOG_OPERATIONS = CATALOG_OPERATION_TABLE
