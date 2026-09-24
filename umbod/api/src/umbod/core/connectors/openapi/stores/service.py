import json
from collections.abc import Mapping
from typing import Optional, Union

from umbod.core.connectors.openapi.stores.catalog_models import (
    OpenApiCatalogHeader,
    OpenApiOperationSummary,
    PersistedOpenApiOperation,
)
from umbod.core.connectors.openapi.management.models import (
    OpenApiConnector,
    OpenApiConnectorCatalog,
    ReplaceCurrentOpenApiCatalog,
)
from umbod.core.connectors.openapi.models import (
    ImportedOpenApiCandidate,
    OpenApiEndpointCapability,
)
from umbod.core.invocation import (
    delete_connector_invocation_policies,
)
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CapabilityActivationStateKey,
    CapabilityActivationStateRecord,
)
from umbod.core.connectors.openapi.stores.schema import (
    CATALOG_OPERATION_CAPABILITY_PROJECTION,
    CATALOG_OPERATION_CATALOG_ID,
    CATALOG_OPERATION_CONNECTOR_ID,
    CATALOG_OPERATION_OPERATION_ID,
    CATALOG_OPERATION_SUMMARY_PROJECTION,
    CATALOG_SOURCE_CATALOG_ID,
    CATALOG_SOURCE_CONNECTOR_ID,
    CATALOG_SOURCE_DOCUMENT_PROJECTION,
    CONNECTOR_DOCUMENT_PROJECTION,
    CONNECTOR_ID,
    CONNECTOR_LIST_PROJECTION,
    CURRENT_CATALOG_HEADER_CONNECTOR_ID,
    CURRENT_CATALOG_HEADER_ID_PROJECTION,
    CatalogOperationKey,
    CatalogOperationRecord,
    CatalogOperationSummaryResult,
    CatalogSourceKey,
    CatalogSourceRecord,
    ConnectorKey,
    ConnectorRecord,
    CurrentCatalogHeaderKey,
    CurrentCatalogHeaderRecord,
)
from umbod.core.persistence.ports import (
    Database,
    DatabaseSession,
    TransactionMode,
)
from umbod.core.persistence.query import (
    AllFields,
    AllOf,
    DeleteQuery,
    Equals,
    InsertCommand,
    NoFilter,
    Not,
    OneOf,
    OrderBy,
    Query,
    Table,
    Unordered,
    UpsertCommand,
)
class OpenApiConnectorStoreService:
    def __init__(
        self,
        database: Database,
        connectors: Table[ConnectorRecord, ConnectorKey],
        headers: Table[CurrentCatalogHeaderRecord, CurrentCatalogHeaderKey],
        sources: Table[CatalogSourceRecord, CatalogSourceKey],
        operations: Table[CatalogOperationRecord, CatalogOperationKey],
        capability_activation_states: Table[CapabilityActivationStateRecord, CapabilityActivationStateKey],
    ) -> None:
        self._database = database
        self._connectors = connectors
        self._headers = headers
        self._sources = sources
        self._operations = operations
        self._capability_activation_states = capability_activation_states

    async def read_current_catalog_header(
        self, connector_id: str
    ) -> Optional[OpenApiCatalogHeader]:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(
                self._headers,
                Query(
                    filter=Equals(CURRENT_CATALOG_HEADER_CONNECTOR_ID, connector_id),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
        return self._header(row) if row is not None else None

    async def current_catalog_exists(self, connector_id: str) -> bool:
        return await self.read_current_catalog_header(connector_id) is not None

    async def current_catalog_connector_ids(self, connector_ids: tuple[str, ...]) -> frozenset[str]:
        requested = frozenset(connector_ids)
        if not requested:
            return frozenset()
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = await session.find_many(
                self._headers,
                Query(
                    filter=OneOf(CURRENT_CATALOG_HEADER_CONNECTOR_ID, tuple(connector_ids)),
                    projection=CURRENT_CATALOG_HEADER_ID_PROJECTION,
                    ordering=Unordered(),
                ),
            )
        return frozenset(row.connector_id for row in rows if row.connector_id in requested)

    async def list_operation_summaries(
        self, connector_id: str
    ) -> tuple[OpenApiOperationSummary, ...]:
        header = await self.read_current_catalog_header(connector_id)
        if header is None:
            return ()
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = await session.find_many(
                self._operations,
                Query(
                    filter=AllOf(
                        (
                            Equals(CATALOG_OPERATION_CONNECTOR_ID, connector_id),
                            Equals(CATALOG_OPERATION_CATALOG_ID, header.catalog_id),
                        )
                    ),
                    projection=CATALOG_OPERATION_SUMMARY_PROJECTION,
                    ordering=OrderBy((CATALOG_OPERATION_OPERATION_ID,)),
                ),
            )
        return tuple(self._summary(row) for row in rows)

    async def read_operation(
        self, connector_id: str, operation_id: str
    ) -> Optional[PersistedOpenApiOperation]:
        header = await self.read_current_catalog_header(connector_id)
        if header is None:
            return None
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(
                self._operations,
                Query(
                    filter=AllOf(
                        (
                            Equals(CATALOG_OPERATION_CONNECTOR_ID, connector_id),
                            Equals(CATALOG_OPERATION_CATALOG_ID, header.catalog_id),
                            Equals(CATALOG_OPERATION_OPERATION_ID, operation_id),
                        )
                    ),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
        return self._operation(row) if row is not None else None

    async def read_current_catalog(self, connector_id: str) -> Optional[OpenApiConnectorCatalog]:
        header = await self.read_current_catalog_header(connector_id)
        if header is None:
            return None
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            source = await session.find_one(
                self._sources,
                Query(
                    filter=AllOf(
                        (
                            Equals(CATALOG_SOURCE_CONNECTOR_ID, connector_id),
                            Equals(CATALOG_SOURCE_CATALOG_ID, header.catalog_id),
                        )
                    ),
                    projection=CATALOG_SOURCE_DOCUMENT_PROJECTION,
                    ordering=Unordered(),
                ),
            )
            rows = await session.find_many(
                self._operations,
                Query(
                    filter=AllOf(
                        (
                            Equals(CATALOG_OPERATION_CONNECTOR_ID, connector_id),
                            Equals(CATALOG_OPERATION_CATALOG_ID, header.catalog_id),
                        )
                    ),
                    projection=CATALOG_OPERATION_CAPABILITY_PROJECTION,
                    ordering=OrderBy((CATALOG_OPERATION_OPERATION_ID,)),
                ),
            )
        if source is None:
            return None
        endpoints = tuple(row.capability for row in rows)
        return OpenApiConnectorCatalog(
            connector_id=connector_id,
            catalog_id=header.catalog_id,
            source_document=source.document,
            candidate=ImportedOpenApiCandidate(
                metadata=header.metadata,
                server_candidates=header.server_candidates,
                endpoints=endpoints,
            ),
            approved_hosts=header.approved_hosts,
            selected_server_url=header.selected_server_url,
            operation_ids=header.operation_ids,
            imported_at=header.imported_at,
        )

    async def save_connector(self, connector: OpenApiConnector) -> None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            await _upsert_document(
                session, self._connectors, connector.connector_id, _dump(connector)
            )

    async def delete_connector(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            deleted = await session.delete(
                self._connectors, DeleteQuery(Equals(CONNECTOR_ID, connector_id))
            )
            if deleted == 0:
                raise KeyError(connector_id)
            await delete_connector_invocation_policies(session, "openapi", connector_id)

    async def get_connector(self, connector_id: str) -> OpenApiConnector:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(
                self._connectors,
                Query(
                    filter=Equals(CONNECTOR_ID, connector_id),
                    projection=CONNECTOR_DOCUMENT_PROJECTION,
                    ordering=Unordered(),
                ),
            )
        if row is None:
            raise KeyError(f"Unknown OpenAPI connector: {connector_id}")
        connector = OpenApiConnector.model_validate_json(row.document)
        if connector.connector_id != connector_id:
            raise KeyError(f"Unknown OpenAPI connector: {connector_id}")
        return connector

    async def list_connectors(self) -> tuple[OpenApiConnector, ...]:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = await session.find_many(
                self._connectors,
                Query(
                    filter=NoFilter(),
                    projection=CONNECTOR_LIST_PROJECTION,
                    ordering=OrderBy((CONNECTOR_ID,)),
                ),
            )
        return tuple(OpenApiConnector.model_validate_json(row.document) for row in rows)

    async def save_catalog(self, catalog: OpenApiConnectorCatalog) -> None:
        connector = await self.get_connector(catalog.connector_id)
        await self.replace_current_catalog(
            ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog)
        )

    async def replace_current_catalog(
        self, replacement: ReplaceCurrentOpenApiCatalog
    ) -> OpenApiConnectorCatalog:
        if replacement.connector.connector_id != replacement.catalog.connector_id:
            raise ValueError("Connector and catalog must belong together")
        catalog = replacement.catalog
        endpoint_operation_ids = tuple(
            endpoint.operation_id for endpoint in catalog.candidate.endpoints
        )
        if len(endpoint_operation_ids) != len(set(endpoint_operation_ids)):
            raise ValueError("Endpoint operation IDs must be unique")
        if len(catalog.operation_ids) != len(set(catalog.operation_ids)):
            raise ValueError("Catalog operation IDs must be unique")
        if set(catalog.operation_ids) != set(endpoint_operation_ids):
            raise ValueError("Catalog operation IDs must match endpoint capabilities")
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await _upsert_document(
                session,
                self._connectors,
                replacement.connector.connector_id,
                _dump(replacement.connector),
            )
            await session.delete(
                self._headers,
                DeleteQuery(Equals(CURRENT_CATALOG_HEADER_CONNECTOR_ID, catalog.connector_id)),
            )
            await session.delete(
                self._sources,
                DeleteQuery(Equals(CATALOG_SOURCE_CONNECTOR_ID, catalog.connector_id)),
            )
            await session.delete(
                self._operations,
                DeleteQuery(Equals(CATALOG_OPERATION_CONNECTOR_ID, catalog.connector_id)),
            )
            await session.insert(
                self._sources,
                InsertCommand(
                    row=CatalogSourceRecord(
                        connector_id=catalog.connector_id,
                        catalog_id=catalog.catalog_id,
                        document=catalog.source_document,
                    )
                ),
            )
            for endpoint in catalog.candidate.endpoints:
                await session.insert(
                    self._operations,
                    InsertCommand(row=self._operation_record(catalog, endpoint)),
                )
            await session.delete(
                self._capability_activation_states,
                DeleteQuery(
                    AllOf(
                        (
                            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, "openapi"),
                            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, catalog.connector_id),
                            Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, "tool"),
                            Not(
                                OneOf(
                                    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
                                    catalog.operation_ids,
                                )
                            ),
                        )
                    )
                ),
            )
            await self._write_header(session, catalog)
        return catalog

    async def _write_header(
        self, session: DatabaseSession, catalog: OpenApiConnectorCatalog
    ) -> None:
        row = CurrentCatalogHeaderRecord(
            connector_id=catalog.connector_id,
            catalog_id=catalog.catalog_id,
            metadata=catalog.candidate.metadata,
            server_candidates=catalog.candidate.server_candidates,
            approved_hosts=catalog.approved_hosts,
            selected_server_url=catalog.selected_server_url,
            operation_ids=catalog.operation_ids,
            imported_at=catalog.imported_at,
        )
        await session.upsert(
            self._headers,
            UpsertCommand(
                key=CurrentCatalogHeaderKey(connector_id=catalog.connector_id),
                row=row,
            ),
        )

    def _operation_record(
        self, catalog: OpenApiConnectorCatalog, endpoint: OpenApiEndpointCapability
    ) -> CatalogOperationRecord:
        return CatalogOperationRecord(
            connector_id=catalog.connector_id,
            catalog_id=catalog.catalog_id,
            operation_id=endpoint.operation_id,
            method=endpoint.method,
            path=endpoint.path,
            summary=endpoint.summary,
            description=endpoint.description,
            tags=_operation_tags(catalog.source_document, endpoint.path, endpoint.method),
            capability=endpoint,
        )

    def _header(self, row: CurrentCatalogHeaderRecord) -> OpenApiCatalogHeader:
        return OpenApiCatalogHeader(
            connector_id=row.connector_id,
            catalog_id=row.catalog_id,
            metadata=row.metadata,
            server_candidates=row.server_candidates,
            approved_hosts=row.approved_hosts,
            selected_server_url=row.selected_server_url,
            operation_ids=row.operation_ids,
            imported_at=row.imported_at,
        )

    def _summary(
        self, row: Union[CatalogOperationRecord, CatalogOperationSummaryResult]
    ) -> OpenApiOperationSummary:
        return OpenApiOperationSummary(
            connector_id=row.connector_id,
            catalog_id=row.catalog_id,
            operation_id=row.operation_id,
            method=row.method,
            path=row.path,
            summary=row.summary,
            description=row.description,
            tags=row.tags,
        )

    def _operation(self, row: CatalogOperationRecord) -> PersistedOpenApiOperation:
        return PersistedOpenApiOperation(summary=self._summary(row), capability=row.capability)


async def _upsert_document(
    session: DatabaseSession,
    table: Table[ConnectorRecord, ConnectorKey],
    connector_id: str,
    document: str,
) -> None:
    await session.upsert(
        table,
        UpsertCommand(
            key=ConnectorKey(connector_id=connector_id),
            row=ConnectorRecord(connector_id=connector_id, document=document),
        ),
    )


def _dump(value: Union[OpenApiConnector, OpenApiConnectorCatalog]) -> str:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _operation_tags(document: Mapping[str, object], path: str, method: str) -> tuple[str, ...]:
    paths = document.get("paths")
    if not isinstance(paths, Mapping):
        return ()
    path_item = paths.get(path)
    if not isinstance(path_item, Mapping):
        return ()
    operation = path_item.get(method)
    if not isinstance(operation, Mapping):
        return ()
    tags = operation.get("tags")
    if not isinstance(tags, list):
        return ()
    return tuple(tag for tag in tags if isinstance(tag, str))
