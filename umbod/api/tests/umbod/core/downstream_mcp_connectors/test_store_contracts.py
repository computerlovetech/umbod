from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, ConnectorDefinitionStoreService, ConnectorHealthStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime, prepared_sqlite_runtime
import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
import pytest
from pydantic import SecretStr, ValidationError
from umbod.core.configuration.exceptions import ConnectorConfigurationDecryptionError
from umbod.core.connectors.downstream_mcp.models import ConnectorHealthy, DiscoveredPrompt, DiscoveredToolWithOutputSchema, DiscoveredResource, DiscoveredResourceTemplate, NoAuthConnectorDefinition, PromptArgument, StaticBearerConnectorDefinition, StaticBearerCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound, ConnectorDefinitionMissing, ConnectorDefinitionStore, ConnectorHealthFound, ConnectorHealthMissing, ConnectorHealthStore, ConnectorIdQuery, PublicPathQuery, CredentialFound, CredentialMissing, EncryptedCredentialStore, ReplaceToolCatalog, SaveConnectorDefinition, SaveConnectorHealth, SaveCredential, ToolCatalogFound, ToolCatalogStore
DefinitionStoreFactory = Callable[[Path], ConnectorDefinitionStore]
CredentialStoreFactory = Callable[[Path], EncryptedCredentialStore]
CatalogStoreFactory = Callable[[Path], ToolCatalogStore]
HealthStoreFactory = Callable[[Path], ConnectorHealthStore]

def _inmemory_definition_store(path: Path) -> ConnectorDefinitionStore:
    return ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE)

def _sqlite_definition_store(path: Path) -> ConnectorDefinitionStore:
    return ConnectorDefinitionStoreService(create_sqlite_runtime(path).database, CONNECTOR_DEFINITION_TABLE)

def _inmemory_credential_store(path: Path) -> EncryptedCredentialStore:
    return EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('correct-key'))

def _sqlite_credential_store(path: Path) -> EncryptedCredentialStore:
    return EncryptedCredentialStoreService(create_sqlite_runtime(path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('correct-key'))

def _inmemory_catalog_store(path: Path) -> ToolCatalogStore:
    return ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE)

def _sqlite_catalog_store(path: Path) -> ToolCatalogStore:
    return ToolCatalogStoreService(create_sqlite_runtime(path).database, TOOL_CATALOG_TABLE)

def _inmemory_health_store(path: Path) -> ConnectorHealthStore:
    return ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE)

def _sqlite_health_store(path: Path) -> ConnectorHealthStore:
    return ConnectorHealthStoreService(create_sqlite_runtime(path).database, CONNECTOR_HEALTH_TABLE)

def _tool(connector_id: str, name: str, description: str='description') -> DiscoveredToolWithOutputSchema:
    return DiscoveredToolWithOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name=name), title=name, description=description, input_schema={'type': 'object'}, output_schema={'type': 'object'})

def _snapshot(connector_id: str, *tools: DiscoveredToolWithOutputSchema) -> ToolCatalogSnapshot:
    return ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2025, 1, 1, tzinfo=UTC), tools=tools)

@pytest.mark.parametrize('store_factory', [_inmemory_definition_store, _sqlite_definition_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_connector_definition_store_round_trips_and_lists_without_credentials(store_factory: DefinitionStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    definition = StaticBearerConnectorDefinition(connector_id='alpha', display_name='Alpha', endpoint_url='https://example.test/mcp')
    await store.save(SaveConnectorDefinition(definition=definition))
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ConnectorDefinitionFound(definition=definition)
    assert (await store.list()).definitions == (definition,)

@pytest.mark.parametrize('store_factory', [_inmemory_definition_store, _sqlite_definition_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_connector_definition_store_enforces_public_path_identity_and_deletes(store_factory: DefinitionStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    first = NoAuthConnectorDefinition(connector_id='zeta', display_name='Zeta', endpoint_url='https://zeta.example.test/mcp', public_path='/mcp/proxies/shared')
    second = NoAuthConnectorDefinition(connector_id='alpha', display_name='Alpha', endpoint_url='https://alpha.example.test/mcp', public_path='/mcp/proxies/shared')
    results = await asyncio.gather(store.save(SaveConnectorDefinition(definition=first)), store.save(SaveConnectorDefinition(definition=second)), return_exceptions=True)
    assert sum((isinstance(result, ValueError) for result in results)) == 1
    definitions = (await store.list()).definitions
    assert len(definitions) == 1
    definition = definitions[0]
    assert await store.get_by_public_path(PublicPathQuery(public_path='/mcp/proxies/shared')) == ConnectorDefinitionFound(definition=definition)
    assert await store.delete(ConnectorIdQuery(connector_id=definition.connector_id)) == ConnectorDefinitionFound(definition=definition)
    assert await store.get_by_public_path(PublicPathQuery(public_path='/mcp/proxies/shared')) == ConnectorDefinitionMissing(connector_id='/mcp/proxies/shared')

@pytest.mark.parametrize('store_factory', [_inmemory_definition_store, _sqlite_definition_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_connector_definition_store_reports_missing_entries(store_factory: DefinitionStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    assert await store.get(ConnectorIdQuery(connector_id='missing')) == ConnectorDefinitionMissing(connector_id='missing')

@pytest.mark.parametrize('store_factory', [_inmemory_credential_store, _sqlite_credential_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_credential_store_round_trips_and_deletes_bearer_credentials(store_factory: CredentialStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    credential = StaticBearerCredentialState(connector_id='alpha', bearer_token=SecretStr('token-value'))
    await store.save(SaveCredential(credential=credential))
    found = await store.get(ConnectorIdQuery(connector_id='alpha'))
    assert isinstance(found, CredentialFound)
    assert found.credential == credential
    assert await store.delete(ConnectorIdQuery(connector_id='alpha')) == CredentialFound(credential=credential)
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == CredentialMissing(connector_id='alpha')

@pytest.mark.parametrize('store_factory', [_inmemory_catalog_store, _sqlite_catalog_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_catalog_reconciliation_classifies_added_changed_removed_and_unchanged(store_factory: CatalogStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    await store.replace(ReplaceToolCatalog(snapshot=_snapshot('alpha', _tool('alpha', 'changed'), _tool('alpha', 'removed'), _tool('alpha', 'same'))))
    result = await store.replace(ReplaceToolCatalog(snapshot=_snapshot('alpha', _tool('alpha', 'added'), _tool('alpha', 'changed', 'new'), _tool('alpha', 'same'))))
    assert tuple((item.downstream_name for item in result.added)) == ('added',)
    assert tuple((item.downstream_name for item in result.changed)) == ('changed',)
    assert tuple((item.downstream_name for item in result.removed)) == ('removed',)
    assert tuple((item.downstream_name for item in result.unchanged)) == ('same',)

@pytest.mark.parametrize('store_factory', [_inmemory_catalog_store, _sqlite_catalog_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_invalid_replacement_preserves_last_known_good_catalog(store_factory: CatalogStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    original = _snapshot('alpha', _tool('alpha', 'stable'))
    await store.replace(ReplaceToolCatalog(snapshot=original))
    with pytest.raises(ValidationError):
        ToolCatalogSnapshot.model_validate({'connector_id': 'alpha', 'discovered_at': datetime.now(UTC), 'tools': [{'identity': {'connector_id': 'alpha', 'downstream_name': 'invalid'}, 'title': 'invalid', 'description': '', 'input_schema': [], 'output_schema_status': 'present', 'output_schema': {}}]})
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ToolCatalogFound(snapshot=original)

@pytest.mark.parametrize('store_factory', [_inmemory_catalog_store, _sqlite_catalog_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_catalog_store_atomically_round_trips_all_discovered_capabilities(store_factory: CatalogStoreFactory, tmp_path: Path) -> None:
    snapshot = ToolCatalogSnapshot(connector_id='alpha', discovered_at=datetime(2025, 1, 1, tzinfo=UTC), tools=(_tool('alpha', 'search'),), prompts=(DiscoveredPrompt(name='summarize', title='Summarize', description='', arguments=(PromptArgument(name='article_id', required=True),)),), resources=(DiscoveredResource(name='Guide', title='Guide', uri='kb://guide', description=''),), resource_templates=(DiscoveredResourceTemplate(name='Article', title='Article', uri_template='kb://articles/{article_id}', description=''),))
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    await store.replace(ReplaceToolCatalog(snapshot=snapshot))
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ToolCatalogFound(snapshot=snapshot)

@pytest.mark.parametrize('store_factory', [_inmemory_health_store, _sqlite_health_store], ids=['inmemory', 'sqlite'])
@pytest.mark.asyncio
async def test_health_store_round_trips_and_deletes_health(store_factory: HealthStoreFactory, tmp_path: Path) -> None:
    database_path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(database_path)
    store = store_factory(database_path)
    health = ConnectorHealthy(connector_id='alpha', checked_at=datetime(2025, 1, 1, tzinfo=UTC))
    await store.save(SaveConnectorHealth(health=health))
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ConnectorHealthFound(health=health)
    assert await store.delete(ConnectorIdQuery(connector_id='alpha')) == ConnectorHealthFound(health=health)
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ConnectorHealthMissing(connector_id='alpha')

@pytest.mark.asyncio
async def test_tool_only_snapshot_defaults_optional_capability_catalogs_to_empty() -> None:
    snapshot = ToolCatalogSnapshot.model_validate({'connector_id': 'alpha', 'discovered_at': '2025-01-01T00:00:00Z', 'tools': []})
    assert snapshot.prompts == ()
    assert snapshot.resources == ()
    assert snapshot.resource_templates == ()

@pytest.mark.asyncio
async def test_catalog_rejects_duplicate_and_cross_connector_tool_identities() -> None:
    with pytest.raises(ValidationError, match='duplicate tool identity'):
        _snapshot('alpha', _tool('alpha', 'same'), _tool('alpha', 'same'))
    with pytest.raises(ValidationError, match='does not match'):
        _snapshot('alpha', _tool('beta', 'tool'))

@pytest.mark.asyncio
async def test_sqlite_credentials_are_encrypted_and_wrong_key_cannot_read(tmp_path: Path) -> None:
    path = tmp_path / 'store.db'
    await prepared_sqlite_runtime(path)
    store = EncryptedCredentialStoreService(create_sqlite_runtime(path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('correct-key'))
    credential = StaticBearerCredentialState(connector_id='alpha', bearer_token=SecretStr('plaintext-token'))
    await store.save(SaveCredential(credential=credential))
    with sqlite3.connect(path) as connection:
        stored = connection.execute('SELECT document FROM downstream_mcp_connector_credentials').fetchone()[0]
    assert 'plaintext-token' not in stored
    with pytest.raises(ConnectorConfigurationDecryptionError):
        await EncryptedCredentialStoreService(create_sqlite_runtime(path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('wrong-key')).get(ConnectorIdQuery(connector_id='alpha'))

@pytest.mark.asyncio
async def test_no_auth_definition_contains_no_credential_material() -> None:
    definition = NoAuthConnectorDefinition(connector_id='alpha', display_name='Alpha', endpoint_url='https://example.test/mcp')
    assert 'token' not in definition.model_dump_json()
