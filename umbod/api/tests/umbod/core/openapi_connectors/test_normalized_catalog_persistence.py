from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from tests.persistence_runtime import prepared_sqlite_runtime
import sqlite3
from pathlib import Path
import pytest
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import OpenApiConnector, OpenApiConnectorCatalog, ReplaceCurrentOpenApiCatalog
from umbod.core.persistence import PersistenceDecodingError
pytestmark = pytest.mark.asyncio

def _catalog(catalog_id: str, operation_id: str) -> OpenApiConnectorCatalog:
    source: dict[str, object] = {'openapi': '3.1.0', 'info': {'title': 'Catalog', 'version': '1'}, 'servers': [{'url': 'https://api.example.test'}], 'paths': {'/items': {'get': {'operationId': operation_id, 'summary': 'List items', 'tags': ['items'], 'responses': {'200': {'description': 'OK'}}}}}}
    candidate = InMemoryOpenApiCandidateImporter().import_candidate(source)
    return OpenApiConnectorCatalog(connector_id='connector', catalog_id=catalog_id, source_document=source, candidate=candidate, approved_hosts=('api.example.test',), selected_server_url='https://api.example.test', operation_ids=(operation_id,), imported_at='now')

def _connector() -> OpenApiConnector:
    return OpenApiConnector(connector_id='connector', display_name='Connector', tool_name_prefix='Connector', capability_description='Connector capabilities', created_at='now', updated_at='now')

async def test_normalized_write_persists_header_source_and_one_operation_without_aggregate(tmp_path: Path) -> None:
    path = tmp_path / 'catalog.sqlite'
    store = OpenApiConnectorStoreService((await prepared_sqlite_runtime(path)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    catalog = _catalog('catalog-1', 'listItems')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=catalog))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'openapi_connector_catalogs'").fetchone() == (0,)
        assert connection.execute('SELECT COUNT(*) FROM openapi_current_catalog_headers').fetchone() == (1,)
        assert connection.execute('SELECT COUNT(*) FROM openapi_catalog_sources').fetchone() == (1,)
        assert connection.execute('SELECT COUNT(*) FROM openapi_catalog_operations').fetchone() == (1,)
    operation = await store.read_operation('connector', 'listItems')
    assert operation is not None
    assert operation.capability == catalog.candidate.endpoints[0]
    assert operation.summary.tags == ('items',)

async def test_corrupt_typed_header_field_fails_at_persistence_boundary(tmp_path: Path) -> None:
    path = tmp_path / 'corrupt-header.sqlite'
    store = OpenApiConnectorStoreService((await prepared_sqlite_runtime(path)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=_catalog('catalog-1', 'listItems')))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE openapi_current_catalog_headers SET operation_ids = 'not-json'")
    with pytest.raises(PersistenceDecodingError, match='openapi_current_catalog_headers.operation_ids'):
        await store.read_current_catalog_header('connector')

async def test_lightweight_reads_do_not_deserialize_source_or_capability(tmp_path: Path) -> None:
    path = tmp_path / 'scope.sqlite'
    store = OpenApiConnectorStoreService((await prepared_sqlite_runtime(path)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    catalog = _catalog('catalog-1', 'listItems')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=catalog))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE openapi_catalog_sources SET document = 'invalid'")
        connection.execute("UPDATE openapi_catalog_operations SET capability = 'invalid'")
    assert await store.read_current_catalog_header('connector') is not None
    assert (await store.list_operation_summaries('connector'))[0].operation_id == 'listItems'

async def test_replacement_removes_stale_operations_and_activation_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / 'restart.sqlite'
    store = OpenApiConnectorStoreService((await prepared_sqlite_runtime(path)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    first = _catalog('catalog-1', 'oldOperation')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=first))
    with sqlite3.connect(path) as connection:
        connection.execute(
            'INSERT INTO capability_activation_states VALUES (?, ?, ?, ?, ?, ?)',
            ('openapi', 'connector', 'tool', 'oldOperation', 'enabled', 'now'),
        )
    replacement = _catalog('catalog-2', 'newOperation')
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=replacement))
    restarted = OpenApiConnectorStoreService((await prepared_sqlite_runtime(path)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    assert await restarted.read_operation('connector', 'oldOperation') is None
    assert await restarted.read_operation('connector', 'newOperation') is not None

async def test_normalized_replacement_rejects_operation_id_divergence_before_writing(tmp_path: Path) -> None:
    path = tmp_path / 'invalid-replacement.sqlite'
    store = OpenApiConnectorStoreService((await prepared_sqlite_runtime(path)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    catalog = _catalog('catalog-1', 'listItems').model_copy(update={'operation_ids': ('different',)})
    with pytest.raises(ValueError, match='must match'):
        await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=_connector(), catalog=catalog))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM openapi_connectors').fetchone() == (0,)
        assert connection.execute('SELECT COUNT(*) FROM openapi_catalog_operations').fetchone() == (0,)
