from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, ConnectorDefinitionStoreService, ConnectorHealthStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_sqlite_runtime, prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.persistence import Database
import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import pytest
import pytest_asyncio
from pydantic import SecretStr, ValidationError
from umbod.core.configuration.exceptions import ConnectorConfigurationDecryptionError
from umbod.core.connectors.downstream_mcp.models import ConnectorHealthy, DiscoveredPrompt, DiscoveredToolWithOutputSchema, DiscoveredResource, DiscoveredResourceTemplate, NoAuthConnectorDefinition, PromptArgument, StaticBearerConnectorDefinition, StaticBearerCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionFound, ConnectorDefinitionMissing, ConnectorHealthFound, ConnectorHealthMissing, ConnectorIdQuery, PublicPathQuery, CredentialFound, CredentialMissing, ReplaceToolCatalog, SaveConnectorDefinition, SaveConnectorHealth, SaveCredential, ToolCatalogFound
@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()

def _tool(connector_id: str, name: str, description: str='description') -> DiscoveredToolWithOutputSchema:
    return DiscoveredToolWithOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name=name), title=name, description=description, input_schema={'type': 'object'}, output_schema={'type': 'object'})

def _snapshot(connector_id: str, *tools: DiscoveredToolWithOutputSchema) -> ToolCatalogSnapshot:
    return ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2025, 1, 1, tzinfo=UTC), tools=tools)

@pytest.mark.asyncio
async def test_connector_definition_store_round_trips_and_lists_without_credentials(database: Database) -> None:
    store = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
    definition = StaticBearerConnectorDefinition(connector_id='alpha', display_name='Alpha', endpoint_url='https://example.test/mcp')
    await store.save(SaveConnectorDefinition(definition=definition))
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ConnectorDefinitionFound(definition=definition)
    assert (await store.list()).definitions == (definition,)

@pytest.mark.asyncio
async def test_connector_definition_store_enforces_public_path_identity_and_deletes(database: Database) -> None:
    store = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
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

@pytest.mark.asyncio
async def test_connector_definition_store_reports_missing_entries(database: Database) -> None:
    store = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
    assert await store.get(ConnectorIdQuery(connector_id='missing')) == ConnectorDefinitionMissing(connector_id='missing')

@pytest.mark.asyncio
async def test_credential_store_round_trips_and_deletes_bearer_credentials(database: Database) -> None:
    store = EncryptedCredentialStoreService(database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('correct-key'))
    credential = StaticBearerCredentialState(connector_id='alpha', bearer_token=SecretStr('token-value'))
    await store.save(SaveCredential(credential=credential))
    found = await store.get(ConnectorIdQuery(connector_id='alpha'))
    assert isinstance(found, CredentialFound)
    assert found.credential == credential
    assert await store.delete(ConnectorIdQuery(connector_id='alpha')) == CredentialFound(credential=credential)
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == CredentialMissing(connector_id='alpha')

@pytest.mark.asyncio
async def test_catalog_reconciliation_classifies_added_changed_removed_and_unchanged(database: Database) -> None:
    store = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    await store.replace(ReplaceToolCatalog(snapshot=_snapshot('alpha', _tool('alpha', 'changed'), _tool('alpha', 'removed'), _tool('alpha', 'same'))))
    result = await store.replace(ReplaceToolCatalog(snapshot=_snapshot('alpha', _tool('alpha', 'added'), _tool('alpha', 'changed', 'new'), _tool('alpha', 'same'))))
    assert tuple((item.downstream_name for item in result.added)) == ('added',)
    assert tuple((item.downstream_name for item in result.changed)) == ('changed',)
    assert tuple((item.downstream_name for item in result.removed)) == ('removed',)
    assert tuple((item.downstream_name for item in result.unchanged)) == ('same',)

@pytest.mark.asyncio
async def test_invalid_replacement_preserves_last_known_good_catalog(database: Database) -> None:
    store = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    original = _snapshot('alpha', _tool('alpha', 'stable'))
    await store.replace(ReplaceToolCatalog(snapshot=original))
    with pytest.raises(ValidationError):
        ToolCatalogSnapshot.model_validate({'connector_id': 'alpha', 'discovered_at': datetime.now(UTC), 'tools': [{'identity': {'connector_id': 'alpha', 'downstream_name': 'invalid'}, 'title': 'invalid', 'description': '', 'input_schema': [], 'output_schema_status': 'present', 'output_schema': {}}]})
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ToolCatalogFound(snapshot=original)

@pytest.mark.asyncio
async def test_catalog_store_atomically_round_trips_all_discovered_capabilities(database: Database) -> None:
    snapshot = ToolCatalogSnapshot(connector_id='alpha', discovered_at=datetime(2025, 1, 1, tzinfo=UTC), tools=(_tool('alpha', 'search'),), prompts=(DiscoveredPrompt(name='summarize', title='Summarize', description='', arguments=(PromptArgument(name='article_id', required=True),)),), resources=(DiscoveredResource(name='Guide', title='Guide', uri='kb://guide', description=''),), resource_templates=(DiscoveredResourceTemplate(name='Article', title='Article', uri_template='kb://articles/{article_id}', description=''),))
    store = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    await store.replace(ReplaceToolCatalog(snapshot=snapshot))
    assert await store.get(ConnectorIdQuery(connector_id='alpha')) == ToolCatalogFound(snapshot=snapshot)

@pytest.mark.asyncio
async def test_health_store_round_trips_and_deletes_health(database: Database) -> None:
    store = ConnectorHealthStoreService(database, CONNECTOR_HEALTH_TABLE)
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
    with closing(sqlite3.connect(path)) as connection:
        stored = connection.execute('SELECT document FROM downstream_mcp_connector_credentials').fetchone()[0]
    assert 'plaintext-token' not in stored
    with pytest.raises(ConnectorConfigurationDecryptionError):
        await EncryptedCredentialStoreService(create_sqlite_runtime(path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('wrong-key')).get(ConnectorIdQuery(connector_id='alpha'))

@pytest.mark.asyncio
async def test_no_auth_definition_contains_no_credential_material() -> None:
    definition = NoAuthConnectorDefinition(connector_id='alpha', display_name='Alpha', endpoint_url='https://example.test/mcp')
    assert 'token' not in definition.model_dump_json()
