from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from tests.persistence_runtime import prepared_inmemory_runtime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import Mock
from umbod.core.persistence import AllFields, Database, DatabaseSession, NoFilter, Query, TransactionMode, Unordered
import asyncio
import json
import pytest
import pytest_asyncio
from umbod.core.connectors.openapi.execution import ExactHttpsDestinationPolicy
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import OpenApiConnector, OpenApiConnectorCatalog, ReplaceCurrentOpenApiCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.fixture
def store(database: Database) -> OpenApiConnectorStore:
    return _store(database)

@pytest.mark.asyncio
async def test_configured_factory_shares_store_during_concurrent_initialization(database: Database) -> None:
    factory = ConfiguredOpenApiConnectorStoreFactory(database)
    (first, second) = await asyncio.gather(factory.create(), factory.create())
    assert first is second

def _records() -> tuple[OpenApiConnector, OpenApiConnectorCatalog]:
    candidate = InMemoryOpenApiCandidateImporter().import_candidate({'openapi': '3.1.0', 'info': {'title': 'T', 'version': '1'}, 'servers': [{'url': 'https://api.example.test/v1'}], 'paths': {'/items/{item}': {'get': {'operationId': 'getItem', 'parameters': [{'name': 'item', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}, {'name': 'tag', 'in': 'query', 'schema': {'type': 'array', 'items': {'type': 'string'}}}, {'name': 'X-Trace', 'in': 'header', 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'OK'}}}}}})
    connector = OpenApiConnector(connector_id='c', display_name='C', tool_name_prefix='C', capability_description='C capabilities', created_at='t', updated_at='t')
    catalog = OpenApiConnectorCatalog(connector_id='c', catalog_id='cat-1', source_document={'b': 1, 'a': 2}, candidate=candidate, approved_hosts=('api.example.test',), selected_server_url='https://api.example.test/v1', operation_ids=('getItem',), imported_at='t')
    return (connector, catalog)

def _store(database: Database) -> OpenApiConnectorStore:
    return OpenApiConnectorStoreService(database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)

@pytest.mark.asyncio
async def test_store_contract_persists_connector_and_current_catalog(store: OpenApiConnectorStore) -> None:
    (connector, catalog) = _records()
    await store.save_connector(connector)
    await store.save_catalog(catalog)
    assert await store.get_connector('c') == connector
    assert await store.read_current_catalog('c') == catalog

@pytest.mark.asyncio
async def test_store_contract_raises_key_error_for_missing_connector(store: OpenApiConnectorStore) -> None:
    with pytest.raises(KeyError, match='missing'):
        await store.get_connector('missing')

@pytest.mark.asyncio
async def test_store_contract_replace_current_catalog_upserts_both_records(store: OpenApiConnectorStore) -> None:
    (connector, catalog) = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    replacement_catalog = catalog.model_copy(update={'catalog_id': 'cat-2'})
    replacement_connector = connector.model_copy(update={'updated_at': 'later'})
    returned = await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=replacement_connector, catalog=replacement_catalog))
    assert returned == replacement_catalog
    assert await store.get_connector('c') == replacement_connector
    assert await store.read_current_catalog('c') == replacement_catalog

@pytest.mark.asyncio
async def test_store_contract_rejects_connector_catalog_mismatch(store: OpenApiConnectorStore) -> None:
    (connector, catalog) = _records()
    mismatched = catalog.model_copy(update={'connector_id': 'other'})
    with pytest.raises(ValueError, match='belong together'):
        await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=mismatched))

@pytest.mark.asyncio
async def test_store_contract_lists_connectors_in_deterministic_order(store: OpenApiConnectorStore) -> None:
    (connector, _) = _records()
    await store.save_connector(connector)
    await store.save_connector(connector.model_copy(update={'connector_id': 'a'}))
    assert tuple((item.connector_id for item in await store.list_connectors())) == ('a', 'c')

@pytest.mark.asyncio
async def test_store_writes_canonical_json(store: OpenApiConnectorStore, database: Database) -> None:
    (connector, catalog) = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    async with database.read_session() as session:
        rows = await session.find_many(CONNECTOR_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    documents = [row.document for row in rows]
    assert len(documents) == 1
    assert all((document == json.dumps(json.loads(document), sort_keys=True, separators=(',', ':')) for document in documents))

@pytest.mark.parametrize('failed_operation', ['upsert', 'insert'], ids=['connector', 'catalog'])
@pytest.mark.asyncio
async def test_replace_rolls_back_catalog_when_write_fails(
    store: OpenApiConnectorStore, database: Database, failed_operation: str,
) -> None:
    (connector, catalog) = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))

    @asynccontextmanager
    async def failing_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with database.session(mode=mode) as session:
            failing = Mock(spec=DatabaseSession, wraps=session)
            getattr(failing, failed_operation).side_effect = RuntimeError('rejected')
            yield failing

    failing_database = Mock(spec=Database, wraps=database)
    failing_database.session.side_effect = failing_session
    failing_store = _store(failing_database)
    changed_catalog = catalog.model_copy(update={'catalog_id': 'cat-2'})
    changed_connector = connector.model_copy(update={'updated_at': 'later'})
    with pytest.raises(RuntimeError, match='rejected'):
        await failing_store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=changed_connector, catalog=changed_catalog))
    assert await store.get_connector('c') == connector
    assert await store.read_current_catalog('c') == catalog

@pytest.mark.asyncio
async def test_store_recreation_preserves_catalog(store: OpenApiConnectorStore, database: Database) -> None:
    (connector, catalog) = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    recreated = _store(database)
    assert await recreated.get_connector('c') == connector
    assert await recreated.read_current_catalog('c') == catalog

@pytest.mark.asyncio
async def test_store_instances_observe_committed_catalog(database: Database) -> None:
    writer = _store(database)
    reader = _store(database)
    (connector, catalog) = _records()
    await writer.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    assert await reader.get_connector('c') == connector
    assert await reader.read_current_catalog('c') == catalog

@pytest.mark.parametrize('url', ['http://api.example.test', 'https://user@api.example.test', 'https://api.example.test:444', 'https://sub.api.example.test'])
def test_destination_policy_rejects_non_exact_or_unsafe_destinations(url: str) -> None:
    with pytest.raises(ValueError):
        ExactHttpsDestinationPolicy().validate(url, ('api.example.test',))
