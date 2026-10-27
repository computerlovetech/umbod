from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.capabilities.catalog import CapabilityCatalog
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import (
    OpenApiConnector,
    OpenApiConnectorCatalog,
    ReplaceCurrentOpenApiCatalog,
)
from umbod.core.connectors.openapi.stores import (
    CATALOG_OPERATION_TABLE,
    CATALOG_SOURCE_TABLE,
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_TABLE,
    OpenApiConnectorStore,
    OpenApiConnectorStoreService,
)
from umbod.core.connectors.openapi.stores.schema import (
    CatalogOperationRecord,
    CurrentCatalogHeaderRecord,
)
from umbod.core.persistence.ports import Database, DatabaseSession, TransactionMode
from umbod.core.persistence.query import DeleteQuery, InsertCommand, NoFilter

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(params=["inmemory", "sqlite"])
async def database(request: pytest.FixtureRequest, tmp_path: Path) -> Database:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "bulk.sqlite")
    )
    return runtime.database


@pytest.fixture
def store(database: Database) -> OpenApiConnectorStore:
    return OpenApiConnectorStoreService(
        database,
        CONNECTOR_TABLE,
        CURRENT_CATALOG_HEADER_TABLE,
        CATALOG_SOURCE_TABLE,
        CATALOG_OPERATION_TABLE,
        CAPABILITY_ACTIVATION_STATE_TABLE,
    )


def _replacement(operation_ids: tuple[str, ...]) -> ReplaceCurrentOpenApiCatalog:
    source: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "Items", "version": "1"},
        "servers": [{"url": "https://api.example.test"}],
        "paths": {
            f"/{operation_id}": {
                "get": {
                    "operationId": operation_id,
                    "summary": operation_id,
                    "tags": ["items"],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {"id": {"type": "string"}}}
                                }
                            },
                        }
                    },
                }
            }
            for operation_id in operation_ids
        },
    }
    candidate = InMemoryOpenApiCandidateImporter().import_candidate(source)
    connector = OpenApiConnector(
        connector_id="connector",
        display_name="Items",
        tool_name_prefix="Items",
        capability_description="Item operations",
        created_at="now",
        updated_at="now",
    )
    catalog = OpenApiConnectorCatalog(
        connector_id="connector",
        catalog_id="current",
        source_document=source,
        candidate=candidate,
        approved_hosts=("api.example.test",),
        selected_server_url="https://api.example.test",
        operation_ids=operation_ids,
        imported_at="now",
    )
    return ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog)


async def test_list_operations_missing_header_returns_empty(
    store: OpenApiConnectorStore,
) -> None:
    await store.save_connector(_replacement(()).connector)
    assert await store.list_operations("connector") == ()
    assert await store.list_operations("missing") == ()


async def test_list_operations_empty_current_catalog_returns_empty(
    store: OpenApiConnectorStore,
) -> None:
    await store.replace_current_catalog(_replacement(()))
    assert await store.list_operations("connector") == ()


async def test_list_operations_isolates_current_catalog_and_connector_without_sources(
    store: OpenApiConnectorStore, database: Database
) -> None:
    replacement = _replacement(("zebra", "alpha"))
    await store.replace_current_catalog(replacement)
    endpoint = replacement.catalog.candidate.endpoints[0]
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.delete(CATALOG_SOURCE_TABLE, DeleteQuery(NoFilter()))
        for connector_id, catalog_id in (("connector", "stale"), ("other", "current")):
            await session.insert(
                CATALOG_OPERATION_TABLE,
                InsertCommand(
                    row=CatalogOperationRecord(
                        connector_id=connector_id,
                        catalog_id=catalog_id,
                        operation_id="excluded",
                        method=endpoint.method,
                        path=endpoint.path,
                        summary=endpoint.summary,
                        description=endpoint.description,
                        tags=(),
                        capability=endpoint,
                    )
                ),
            )
    operations = await store.list_operations("connector")
    assert tuple(operation.summary.operation_id for operation in operations) == ("alpha", "zebra")
    assert tuple(operation.capability for operation in operations) == tuple(
        sorted(replacement.catalog.candidate.endpoints, key=lambda item: item.operation_id)
    )
    assert all(operation.summary.tags == ("items",) for operation in operations)
    assert await store.list_operations("other") == ()


async def test_list_operations_does_not_fall_back_to_stale_catalog(
    store: OpenApiConnectorStore, database: Database
) -> None:
    replacement = _replacement(("old",))
    await store.replace_current_catalog(replacement)
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.delete(CURRENT_CATALOG_HEADER_TABLE, DeleteQuery(NoFilter()))
        await session.insert(
            CURRENT_CATALOG_HEADER_TABLE,
            InsertCommand(
                row=CurrentCatalogHeaderRecord(
                    connector_id="connector",
                    catalog_id="new-empty",
                    metadata=replacement.catalog.candidate.metadata,
                    server_candidates=replacement.catalog.candidate.server_candidates,
                    approved_hosts=replacement.catalog.approved_hosts,
                    selected_server_url=replacement.catalog.selected_server_url,
                    operation_ids=(),
                    imported_at="later",
                )
            ),
        )
    assert await store.list_operations("connector") == ()


@pytest.mark.parametrize("operation_count", [1, 20])
async def test_public_catalogue_uses_constant_reads_and_one_operation_session(
    store: OpenApiConnectorStore,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    operation_count: int,
) -> None:
    replacement = _replacement(tuple(f"operation{index:02}" for index in range(operation_count)))
    await store.replace_current_catalog(replacement)
    original_session = database.session
    sessions: list[Mock] = []

    @asynccontextmanager
    async def recording_session(mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with original_session(mode=mode) as session:
            recorded = Mock(spec=DatabaseSession, wraps=session)
            sessions.append(recorded)
            yield recorded

    monkeypatch.setattr(database, "session", recording_session)
    catalog: CapabilityCatalog = StoreBackedOpenApiCapabilityCatalog(store)
    capabilities = await catalog.list_capabilities()
    assert len(capabilities) == operation_count
    assert len(sessions) == 2
    assert sessions[0].find_many.await_count == 1
    assert sessions[1].find_one.await_count == 1
    assert sessions[1].find_many.await_count == 1
    assert sessions[1].find_one.call_args.args[0] == CURRENT_CATALOG_HEADER_TABLE
    assert sessions[1].find_many.call_args.args[0] == CATALOG_OPERATION_TABLE
    for capability in capabilities:
        assert capability == await catalog.resolve(capability.identity)
