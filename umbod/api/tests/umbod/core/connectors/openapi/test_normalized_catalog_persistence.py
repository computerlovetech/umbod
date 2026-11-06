from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.activation.stores.schema import CapabilityActivationStateRecord
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import OpenApiConnector, OpenApiConnectorCatalog, ReplaceCurrentOpenApiCatalog
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStore, OpenApiConnectorStoreService
from umbod.core.connectors.openapi.stores.schema import CATALOG_OPERATION_SUMMARY_PROJECTION
from umbod.core.persistence import AllFields, Database, DatabaseSession, InsertCommand, NoFilter, PersistenceDecodingError, Query, TransactionMode, Unordered
from umbod.core.persistence.ports import ReadSession

pytestmark = pytest.mark.asyncio


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


def _store(database: Database) -> OpenApiConnectorStore:
    return OpenApiConnectorStoreService(database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)


def _catalog(catalog_id: str, operation_id: str) -> OpenApiConnectorCatalog:
    source: dict[str, object] = {'openapi': '3.1.0', 'info': {'title': 'Catalog', 'version': '1'}, 'servers': [{'url': 'https://api.example.test'}], 'paths': {'/items': {'get': {'operationId': operation_id, 'summary': 'List items', 'tags': ['items'], 'responses': {'200': {'description': 'OK'}}}}}}
    candidate = InMemoryOpenApiCandidateImporter().import_candidate(source)
    return OpenApiConnectorCatalog(connector_id='connector', catalog_id=catalog_id, source_document=source, candidate=candidate, approved_hosts=('api.example.test',), selected_server_url='https://api.example.test', operation_ids=(operation_id,), imported_at='now')


def _connector() -> OpenApiConnector:
    return OpenApiConnector(connector_id='connector', display_name='Connector', tool_name_prefix='Connector', capability_description='Connector capabilities', created_at='now', updated_at='now')


async def test_normalized_write_persists_header_source_and_one_operation(store: OpenApiConnectorStore, database: Database) -> None:
    catalog = _catalog('catalog-1', 'listItems')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=catalog))
    async with database.read_session() as session:
        query = Query(NoFilter(), AllFields(), Unordered())
        assert len(await session.find_many(CURRENT_CATALOG_HEADER_TABLE, query)) == 1
        assert len(await session.find_many(CATALOG_SOURCE_TABLE, query)) == 1
        assert len(await session.find_many(CATALOG_OPERATION_TABLE, query)) == 1
    operation = await store.read_operation('connector', 'listItems')
    assert operation is not None
    assert operation.capability == catalog.candidate.endpoints[0]
    assert operation.summary.tags == ('items',)


async def test_header_read_propagates_persistence_decoding_failure(store: OpenApiConnectorStore, database: Database) -> None:
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=_catalog('catalog-1', 'listItems')))
    failure = PersistenceDecodingError('openapi_current_catalog_headers', 'operation_ids', ValueError('invalid JSON'))

    @asynccontextmanager
    async def unreadable_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with database.session(mode=mode) as session:
            unreadable = Mock(spec=DatabaseSession, wraps=session)
            unreadable.find_one.side_effect = failure
            yield unreadable

    unreadable_database = Mock(spec=Database, wraps=database)
    unreadable_database.session.side_effect = unreadable_session
    with pytest.raises(PersistenceDecodingError, match='openapi_current_catalog_headers.operation_ids') as captured:
        await _store(unreadable_database).read_current_catalog_header('connector')
    assert captured.value is failure


async def test_lightweight_reads_do_not_deserialize_source_or_capability(store: OpenApiConnectorStore, database: Database) -> None:
    catalog = _catalog('catalog-1', 'listItems')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=catalog))
    sessions: list[Mock] = []

    @asynccontextmanager
    async def recording_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with database.session(mode=mode) as session:
            recorded = Mock(spec=DatabaseSession, wraps=session)
            sessions.append(recorded)
            yield recorded

    @asynccontextmanager
    async def recording_read_session() -> AsyncIterator[ReadSession]:
        async with database.read_session() as session:
            recorded = Mock(spec=ReadSession, wraps=session)
            sessions.append(recorded)
            yield recorded

    recording_database = Mock(spec=Database, wraps=database)
    recording_database.session.side_effect = recording_session
    recording_database.read_session.side_effect = recording_read_session
    reader = _store(recording_database)
    assert await reader.read_current_catalog_header('connector') is not None
    assert (await reader.list_operation_summaries('connector'))[0].operation_id == 'listItems'
    reads = [
        call for session in sessions
        for call in (*session.find_one.call_args_list, *session.find_many.call_args_list)
    ]
    assert all(call.args[0] != CATALOG_SOURCE_TABLE for call in reads)
    operation_queries = [call.args[1] for call in reads if call.args[0] == CATALOG_OPERATION_TABLE]
    assert operation_queries
    assert all(query.projection == CATALOG_OPERATION_SUMMARY_PROJECTION for query in operation_queries)


async def test_replacement_removes_stale_operations_and_activation_across_store_recreation(store: OpenApiConnectorStore, database: Database) -> None:
    first = _catalog('catalog-1', 'oldOperation')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=first))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(
            CAPABILITY_ACTIVATION_STATE_TABLE,
            InsertCommand(row=CapabilityActivationStateRecord(
                connector_kind='openapi', connector_id='connector', capability_kind='tool',
                capability_key='oldOperation', status='enabled', updated_at='now',
            )),
        )
    replacement = _catalog('catalog-2', 'newOperation')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=replacement))
    recreated = _store(database)
    assert await recreated.read_operation('connector', 'oldOperation') is None
    assert await recreated.read_operation('connector', 'newOperation') is not None
    async with database.read_session() as session:
        assert await session.find_many(CAPABILITY_ACTIVATION_STATE_TABLE, Query(NoFilter(), AllFields(), Unordered())) == ()


async def test_normalized_replacement_rejects_operation_id_divergence_before_writing(store: OpenApiConnectorStore, database: Database) -> None:
    catalog = _catalog('catalog-1', 'listItems').model_copy(update={'operation_ids': ('different',)})
    with pytest.raises(ValueError, match='must match'):
        await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=catalog))
    async with database.read_session() as session:
        assert await session.find_many(CONNECTOR_TABLE, Query(NoFilter(), AllFields(), Unordered())) == ()
        assert await session.find_many(CATALOG_OPERATION_TABLE, Query(NoFilter(), AllFields(), Unordered())) == ()
