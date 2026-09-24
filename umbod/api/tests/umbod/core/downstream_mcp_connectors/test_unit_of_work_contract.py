from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE, create_capability_activation_store
from umbod.core.activation.stores.service import CapabilityActivationStoreService
from umbod.core.connectors.downstream_mcp.management import DownstreamConnectorUnitOfWorkService, InMemoryDownstreamConnectorUnitOfWork, utc_clock
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, ConnectorDefinitionStoreService, ConnectorHealthStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime, prepared_sqlite_runtime
import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
import pytest
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolNameConflictError
from umbod.core.connectors.downstream_mcp.models import ConnectorHealthy, DiscoveredToolWithoutOutputSchema, StaticBearerConnectorDefinition, StaticBearerCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore, ConnectorHealthStore, ConnectorIdQuery, CredentialFound, EncryptedCredentialStore, ToolCatalogFound, ToolCatalogStore
from umbod.core.connectors.downstream_mcp.management import CreateDownstreamConnectorAggregate, DownstreamConnectorUnitOfWork, PreservePublication, ReconcileActivation, ReplaceCatalog, ReplaceCredential, ReplaceHealth, UpdatePublishedConnectorPrefix

class AggregateHarness(Protocol):
    unit_of_work: DownstreamConnectorUnitOfWork
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    catalogs: ToolCatalogStore
    health: ConnectorHealthStore
    publishing: ConnectorPublishingStore

class Harness:

    def __init__(self, unit_of_work: DownstreamConnectorUnitOfWork, definitions: ConnectorDefinitionStore, credentials: EncryptedCredentialStore, catalogs: ToolCatalogStore, health: ConnectorHealthStore, publishing: ConnectorPublishingStore) -> None:
        self.unit_of_work = unit_of_work
        self.definitions = definitions
        self.credentials = credentials
        self.catalogs = catalogs
        self.health = health
        self.publishing = publishing

def _command() -> CreateDownstreamConnectorAggregate:
    checked_at = datetime(2026, 1, 2, tzinfo=UTC)
    return CreateDownstreamConnectorAggregate(definition=StaticBearerConnectorDefinition(connector_id='alpha', display_name='Alpha', capability_description='Manage downstream tools', endpoint_url='https://example.test/mcp'), credential=ReplaceCredential(credential=StaticBearerCredentialState(connector_id='alpha', bearer_token='secret-token')), catalog=ReplaceCatalog(snapshot=ToolCatalogSnapshot(connector_id='alpha', discovered_at=checked_at, tools=())), health=ReplaceHealth(health=ConnectorHealthy(connector_id='alpha', checked_at=checked_at)), activation=ReconcileActivation(operation_names=()), publication=PreservePublication())

async def _inmemory(_: Path, fault: Callable[[str], None]) -> AggregateHarness:
    definitions = ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('unit-of-work-secret'))
    catalogs = ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE)
    health = ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE)
    database = create_inmemory_runtime().database
    activations = CapabilityActivationStoreService(database, CAPABILITY_ACTIVATION_STATE_TABLE)
    publishing = ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
    return Harness(InMemoryDownstreamConnectorUnitOfWork(definitions, credentials, catalogs, health, activations, publishing, fault), definitions, credentials, catalogs, health, publishing)

async def _sqlite(path: Path, fault: Callable[[str], None]) -> AggregateHarness:
    definitions = ConnectorDefinitionStoreService(create_sqlite_runtime(path).database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(create_sqlite_runtime(path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('unit-of-work-secret'))
    catalogs = ToolCatalogStoreService(create_sqlite_runtime(path).database, TOOL_CATALOG_TABLE)
    health = ConnectorHealthStoreService(create_sqlite_runtime(path).database, CONNECTOR_HEALTH_TABLE)
    database = (await prepared_sqlite_runtime(path)).database
    await create_capability_activation_store(database)
    publishing = await create_connector_publishing_store(database)
    return Harness(DownstreamConnectorUnitOfWorkService(create_sqlite_runtime(path).database, AuthenticatedTextCipher('unit-of-work-secret'), fault, utc_clock), definitions, credentials, catalogs, health, publishing)

@pytest.mark.parametrize('factory', (_inmemory, _sqlite), ids=('inmemory', 'sqlite'))
@pytest.mark.asyncio
async def test_atomic_create_persists_complete_aggregate(tmp_path: Path, factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]]) -> None:
    database_path = tmp_path / 'aggregate.sqlite3'
    await prepared_sqlite_runtime(database_path)
    harness = await factory(database_path, lambda phase: None)
    await harness.unit_of_work.create(_command())
    query = ConnectorIdQuery(connector_id='alpha')
    assert (await harness.definitions.get(query)).found is True
    credential = await harness.credentials.get(query)
    assert isinstance(credential, CredentialFound)
    assert credential.credential.bearer_token.get_secret_value() == 'secret-token'
    assert isinstance(await harness.catalogs.get(query), ToolCatalogFound)
    assert (await harness.health.get(query)).found is True

@pytest.mark.parametrize('factory', (_inmemory, _sqlite), ids=('inmemory', 'sqlite'))
@pytest.mark.parametrize('failed_phase', ('definition', 'credential', 'catalog', 'health', 'activation'))
@pytest.mark.asyncio
async def test_create_failure_at_each_phase_rolls_back_all_state(tmp_path: Path, factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]], failed_phase: str) -> None:

    def fail(phase: str) -> None:
        if phase == failed_phase:
            raise RuntimeError(f'injected {phase} failure')
    database_path = tmp_path / f'{failed_phase}.sqlite3'
    await prepared_sqlite_runtime(database_path)
    harness = await factory(database_path, fail)
    with pytest.raises(RuntimeError, match=f'injected {failed_phase} failure'):
        await harness.unit_of_work.create(_command())
    query = ConnectorIdQuery(connector_id='alpha')
    assert (await harness.definitions.get(query)).found is False
    assert (await harness.credentials.get(query)).found is False
    assert (await harness.catalogs.get(query)).found is False
    assert (await harness.health.get(query)).found is False

def _published_prefix_command(connector_id: str, tool_name_prefix: str) -> CreateDownstreamConnectorAggregate:
    checked_at = datetime(2026, 1, 2, tzinfo=UTC)
    return CreateDownstreamConnectorAggregate(definition=StaticBearerConnectorDefinition(connector_id=connector_id, display_name=connector_id.title(), tool_name_prefix=tool_name_prefix, capability_description=f'Manage {connector_id} tools', endpoint_url=f'https://{connector_id}.test/mcp'), credential=ReplaceCredential(credential=StaticBearerCredentialState(connector_id=connector_id, bearer_token='secret-token')), catalog=ReplaceCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=checked_at, tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name='search'), title='Search', description='Search', input_schema={'type': 'object'}),))), health=ReplaceHealth(health=ConnectorHealthy(connector_id=connector_id, checked_at=checked_at)), activation=ReconcileActivation(operation_names=('search',)), publication=PreservePublication())

@pytest.mark.asyncio
async def test_sqlite_concurrent_prefix_updates_commit_only_one_conflicting_claim(tmp_path: Path) -> None:
    database_path = tmp_path / 'concurrent-prefix.sqlite3'
    await prepared_sqlite_runtime(database_path)
    first = await _sqlite(database_path, lambda phase: None)
    second = await _sqlite(database_path, lambda phase: None)
    alpha = _published_prefix_command('alpha', 'Alpha')
    beta = _published_prefix_command('beta', 'Beta')
    await first.unit_of_work.create(alpha)
    await first.unit_of_work.create(beta)
    await first.publishing.publish_connector('alpha')
    await first.publishing.publish_connector('beta')
    results = await asyncio.gather(first.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(definition=alpha.definition.model_copy(update={'tool_name_prefix': 'Shared'}), native_identities=())), second.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(definition=beta.definition.model_copy(update={'tool_name_prefix': 'Shared'}), native_identities=())), return_exceptions=True)
    assert sum((result is None for result in results)) == 1
    assert sum((isinstance(result, PublicToolNameConflictError) for result in results)) == 1
    stored_alpha = await first.definitions.get(ConnectorIdQuery(connector_id='alpha'))
    stored_beta = await first.definitions.get(ConnectorIdQuery(connector_id='beta'))
    assert {stored_alpha.definition.tool_name_prefix, stored_beta.definition.tool_name_prefix} in ({'Shared', 'Alpha'}, {'Shared', 'Beta'})
