from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import CATALOG_OPERATION_TABLE, CATALOG_SOURCE_TABLE, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, OpenApiConnectorStoreService
from umbod.core.connectors.openapi.stores.factories import ConfiguredOpenApiConnectorStoreFactory
from tests.persistence_runtime import create_inmemory_runtime
from tests.persistence_runtime import prepared_persistence_runtime
from umbod.config import AppConfig
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Awaitable, Callable
import pytest
from umbod.core.connectors.openapi.execution import ExactHttpsDestinationPolicy
from umbod.core.connectors.openapi.importing import InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import OpenApiConnector, OpenApiConnectorCatalog, ReplaceCurrentOpenApiCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
StoreFactory = Callable[[Path], Awaitable[OpenApiConnectorStore]]

@pytest.mark.asyncio
async def test_configured_inmemory_factory_shares_store_during_concurrent_initialization(tmp_path: Path) -> None:
    factory = ConfiguredOpenApiConnectorStoreFactory(create_inmemory_runtime().database)
    (first, second) = await asyncio.gather(factory.create(), factory.create())
    assert first is second

def _records() -> tuple[OpenApiConnector, OpenApiConnectorCatalog]:
    candidate = InMemoryOpenApiCandidateImporter().import_candidate({'openapi': '3.1.0', 'info': {'title': 'T', 'version': '1'}, 'servers': [{'url': 'https://api.example.test/v1'}], 'paths': {'/items/{item}': {'get': {'operationId': 'getItem', 'parameters': [{'name': 'item', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}, {'name': 'tag', 'in': 'query', 'schema': {'type': 'array', 'items': {'type': 'string'}}}, {'name': 'X-Trace', 'in': 'header', 'schema': {'type': 'string'}}], 'responses': {'200': {'description': 'OK'}}}}}})
    connector = OpenApiConnector(connector_id='c', display_name='C', tool_name_prefix='C', capability_description='C capabilities', created_at='t', updated_at='t')
    catalog = OpenApiConnectorCatalog(connector_id='c', catalog_id='cat-1', source_document={'b': 1, 'a': 2}, candidate=candidate, approved_hosts=('api.example.test',), selected_server_url='https://api.example.test/v1', operation_ids=('getItem',), imported_at='t')
    return (connector, catalog)

async def _in_memory(_path: Path) -> OpenApiConnectorStore:
    return OpenApiConnectorStoreService(create_inmemory_runtime().database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)

async def _sqlite(path: Path) -> OpenApiConnectorStore:
    return OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)

@pytest.mark.parametrize('factory', [_in_memory, _sqlite], ids=['in_memory', 'sqlite'])
@pytest.mark.asyncio
async def test_store_contract_persists_connector_and_current_catalog(tmp_path: Path, factory: StoreFactory) -> None:
    store = await factory(tmp_path / 'store.sqlite')
    (connector, catalog) = _records()
    await store.save_connector(connector)
    await store.save_catalog(catalog)
    assert await store.get_connector('c') == connector
    assert await store.read_current_catalog('c') == catalog

@pytest.mark.parametrize('factory', [_in_memory, _sqlite], ids=['in_memory', 'sqlite'])
@pytest.mark.asyncio
async def test_store_contract_raises_key_error_for_missing_connector(tmp_path: Path, factory: StoreFactory) -> None:
    store = await factory(tmp_path / 'store.sqlite')
    with pytest.raises(KeyError, match='missing'):
        await store.get_connector('missing')

@pytest.mark.parametrize('factory', [_in_memory, _sqlite], ids=['in_memory', 'sqlite'])
@pytest.mark.asyncio
async def test_store_contract_replace_current_catalog_upserts_both_records(tmp_path: Path, factory: StoreFactory) -> None:
    store = await factory(tmp_path / 'store.sqlite')
    (connector, catalog) = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    replacement_catalog = catalog.model_copy(update={'catalog_id': 'cat-2'})
    replacement_connector = connector.model_copy(update={'updated_at': 'later'})
    returned = await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=replacement_connector, catalog=replacement_catalog))
    assert returned == replacement_catalog
    assert await store.get_connector('c') == replacement_connector
    assert await store.read_current_catalog('c') == replacement_catalog

@pytest.mark.parametrize('factory', [_in_memory, _sqlite], ids=['in_memory', 'sqlite'])
@pytest.mark.asyncio
async def test_store_contract_rejects_connector_catalog_mismatch(tmp_path: Path, factory: StoreFactory) -> None:
    store = await factory(tmp_path / 'store.sqlite')
    (connector, catalog) = _records()
    mismatched = catalog.model_copy(update={'connector_id': 'other'})
    with pytest.raises(ValueError, match='belong together'):
        await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=mismatched))

@pytest.mark.parametrize('factory', [_in_memory, _sqlite], ids=['in_memory', 'sqlite'])
@pytest.mark.asyncio
async def test_store_contract_lists_connectors_in_deterministic_order(tmp_path: Path, factory: StoreFactory) -> None:
    store = await factory(tmp_path / 'ordered.sqlite')
    (connector, _) = _records()
    await store.save_connector(connector)
    await store.save_connector(connector.model_copy(update={'connector_id': 'a'}))
    assert tuple((item.connector_id for item in await store.list_connectors())) == ('a', 'c')

@pytest.mark.asyncio
async def test_sqlite_store_writes_canonical_json(tmp_path: Path) -> None:
    path = tmp_path / 'store.sqlite'
    (connector, catalog) = _records()
    store = OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    with sqlite3.connect(path) as connection:
        documents = [row[0] for row in connection.execute('SELECT document FROM openapi_connectors').fetchall()]
    assert all((document == json.dumps(json.loads(document), sort_keys=True, separators=(',', ':')) for document in documents))

@pytest.mark.asyncio
async def test_sqlite_replace_rolls_back_catalog_when_connector_write_fails(tmp_path: Path) -> None:
    path = tmp_path / 'store.sqlite'
    store = OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    (connector, catalog) = _records()
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER reject_connector_update BEFORE UPDATE ON openapi_connectors BEGIN SELECT RAISE(ABORT, 'rejected'); END")
    changed_catalog = catalog.model_copy(update={'catalog_id': 'cat-2'})
    changed_connector = connector.model_copy(update={'updated_at': 'later'})
    with pytest.raises(sqlite3.IntegrityError, match='rejected'):
        await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=changed_connector, catalog=changed_catalog))
    assert await store.get_connector('c') == connector
    assert await store.read_current_catalog('c') == catalog

@pytest.mark.asyncio
async def test_sqlite_store_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / 'store.sqlite'
    (connector, catalog) = _records()
    store = OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    await store.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    restarted = OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    assert await restarted.get_connector('c') == connector
    assert await restarted.read_current_catalog('c') == catalog

@pytest.mark.asyncio
async def test_independently_constructed_sqlite_stores_observe_committed_catalog(tmp_path: Path) -> None:
    path = tmp_path / 'shared.sqlite'
    writer = OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    reader = OpenApiConnectorStoreService((await prepared_persistence_runtime(AppConfig(connector_store={'type': 'sqlite', 'sqlite_path': str(path)}).connector_store)).database, CONNECTOR_TABLE, CURRENT_CATALOG_HEADER_TABLE, CATALOG_SOURCE_TABLE, CATALOG_OPERATION_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE)
    (connector, catalog) = _records()
    await writer.replace_current_catalog(ReplaceCurrentOpenApiCatalog(connector=connector, catalog=catalog))
    assert await reader.get_connector('c') == connector
    assert await reader.read_current_catalog('c') == catalog

@pytest.mark.parametrize('url', ['http://api.example.test', 'https://user@api.example.test', 'https://api.example.test:444', 'https://sub.api.example.test'])
def test_destination_policy_rejects_non_exact_or_unsafe_destinations(url: str) -> None:
    with pytest.raises(ValueError):
        ExactHttpsDestinationPolicy().validate(url, ('api.example.test',))
