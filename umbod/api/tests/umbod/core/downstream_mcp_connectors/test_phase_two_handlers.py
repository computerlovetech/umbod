from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.connectors.downstream_mcp.management import InMemoryDownstreamConnectorUnitOfWork
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, ConnectorDefinitionStoreService, ConnectorHealthStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_inmemory_runtime
from datetime import UTC, datetime
from typing import Any
import pytest
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError, PublicToolNameValidator
from umbod.core.activation import (
    ActivationStatus,
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, StaticBearerCreateConnectorDefinition, NoAuthCredentialState, StaticBearerConnectorDefinition, StaticBearerCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.errors import DownstreamConnectorUnavailableError
from umbod.core.connectors.downstream_mcp.management import DownstreamConnectorCreator, DownstreamConnectorDeleter, DownstreamConnectorPreparation, DownstreamConnectorQueries, DownstreamConnectorUpdater
from umbod.core.connectors.downstream_mcp.connection import DownstreamMcpConnectionConfiguration
from umbod.core.connectors.downstream_mcp.probe import DiscoveredCapabilities, ProbeCapabilities, ProbeResult
from umbod.core.connectors.downstream_mcp.publishing import DownstreamConnectorPublisher
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, CredentialFound, ReplaceToolCatalog, SaveConnectorDefinition

class PublicToolIdentitySourceFake:

    def __init__(self, identities: tuple[PublicToolIdentity, ...]) -> None:
        self._identities = identities

    async def identities(self) -> tuple[PublicToolIdentity, ...]:
        return self._identities

class SuccessfulDownstreamMcpProbe:

    async def probe(self, configuration: DownstreamMcpConnectionConfiguration) -> ProbeResult:
        return ProbeCapabilities(capabilities=DiscoveredCapabilities(tools=()), endpoint_url=configuration.endpoint_url)

class FixedIdGenerator:

    def new_id(self) -> str:
        return 'alpha'

class AvailableIdentities:

    async def ensure_available(self, requested: Any) -> None:
        return None

class UnusedDiscovery:

    async def discover(self, command: Any) -> Any:
        raise AssertionError('discovery was not expected')

class ActivationFake:

    def __init__(self) -> None:
        self.statuses: dict[CapabilityRef, ActivationStatus] = {}

    async def get_status(self, ref: CapabilityRef) -> ActivationStatus:
        return self.statuses.get(ref, ActivationStatus.DISABLED)

    async def set_status(self, ref: CapabilityRef, status: ActivationStatus) -> None:
        self.statuses[ref] = status

    async def set_statuses(self, states: tuple[CapabilityActivationState, ...]) -> None:
        for state in states:
            self.statuses[state.ref] = state.activation_status

    async def reconcile(
        self,
        connector_kind: str,
        connector_id: str,
        capability_kind: str,
        current_keys: tuple[str, ...],
    ) -> None:
        allowed = set(current_keys)
        self.statuses = {
            ref: status
            for (ref, status) in self.statuses.items()
            if ref.connector_kind != connector_kind
            or ref.connector_id != connector_id
            or ref.capability_kind != capability_kind
            or ref.capability_key in allowed
        }

class PermissionsFake:

    async def list_all_group_permissions(self) -> tuple[Any, ...]:
        return ()

    def list_group_permissions(self, group_id: str) -> Any:
        raise KeyError(group_id)

class EventStreamFake:

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.failure: RuntimeError | None = None

    async def append(self, event: Any) -> Any:
        if self.failure is not None:
            raise self.failure
        self.events.append(event)
        return event

class FailOnceProxy:

    def __init__(self, target: Any, method: str) -> None:
        self.target = target
        self.method = method
        self.failed = False

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self.target, name)
        if name != self.method:
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            if not self.failed:
                self.failed = True
                raise RuntimeError(f'injected {name} failure')
            return attribute(*args, **kwargs)
        return invoke

class DownstreamConnectorFixture:

    def __init__(self, definitions: Any, credentials: Any, catalogs: Any, health: Any, discovery: Any, activation_store: Any, publishing: Any, activation: Any, permissions: Any, events: Any, ids: Any, identities: Any, probe: Any, unit_of_work: Any, native_identities: tuple[Any, ...]=()) -> None:
        self.queries = DownstreamConnectorQueries(definitions, credentials, catalogs, health, publishing)
        preparation = DownstreamConnectorPreparation(probe)
        self.creator = DownstreamConnectorCreator(definitions, ids, identities, preparation, unit_of_work)
        validator = PublicToolNameValidator()
        identity_source = PublicToolIdentitySourceFake(native_identities)
        self.updater = DownstreamConnectorUpdater(credentials, catalogs, publishing, events, unit_of_work, preparation, self.queries, validator, identity_source)
        self.publisher = DownstreamConnectorPublisher(publishing, events, self.queries, validator, identity_source)
        self.deleter = DownstreamConnectorDeleter(permissions, publishing, events, unit_of_work, self.queries)

    async def create(self, request: Any) -> Any:
        return await self.creator.create(request)

    async def update(self, definition: Any, replacement_token: str) -> Any:
        current = await self.queries.get(definition.connector_id)
        return await self.updater.update(current, definition, replacement_token)

    async def publish(self, connector_id: str) -> None:
        await self.publisher.publish(connector_id)

    async def delete(self, connector_id: str) -> Any:
        return await self.deleter.delete(connector_id)

    async def get(self, connector_id: str) -> Any:
        return await self.queries.get(connector_id)

    async def catalog(self, connector_id: str) -> Any:
        return await self.queries.catalog(connector_id)

    async def health(self, connector_id: str) -> Any:
        return await self.queries.health(connector_id)

def definition(endpoint: str) -> StaticBearerConnectorDefinition:
    return StaticBearerConnectorDefinition(connector_id='alpha', display_name='Alpha', capability_description='Manage downstream tools', endpoint_url=endpoint)

def service(definitions: Any, credentials: Any, catalogs: Any, health: Any, native_identities: tuple[Any, ...]=()) -> tuple[DownstreamConnectorFixture, Any, Any, Any, Any, ConnectorPublishingStoreService, EventStreamFake]:
    publishing = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    events = EventStreamFake()
    activation = ActivationFake()
    return (DownstreamConnectorFixture(definitions, credentials, catalogs, health, UnusedDiscovery(), activation, publishing, activation, PermissionsFake(), events, FixedIdGenerator(), AvailableIdentities(), SuccessfulDownstreamMcpProbe(), InMemoryDownstreamConnectorUnitOfWork(definitions, credentials, catalogs, health, activation, publishing, lambda phase: None), native_identities), definitions, credentials, catalogs, health, publishing, events)

def standard_service() -> tuple[DownstreamConnectorFixture, Any, Any, Any, Any, ConnectorPublishingStoreService, EventStreamFake]:
    return service(ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE), EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('phase-two-secret')), ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE), ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE))

async def create_configured(connector_service: DownstreamConnectorFixture) -> None:
    await connector_service.create(StaticBearerCreateConnectorDefinition(display_name='Alpha', capability_description='Manage downstream tools', endpoint_url='https://example.test/mcp', public_path='/mcp/proxies/alpha', bearer_token='old-token'))

def tool_snapshot(connector_id: str, operation_name: str) -> ToolCatalogSnapshot:
    return ToolCatalogSnapshot(connector_id=connector_id, discovered_at=datetime(2026, 1, 1, tzinfo=UTC), tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name=operation_name), title=operation_name, description=operation_name, input_schema={'type': 'object'}),))

@pytest.mark.asyncio
@pytest.mark.parametrize('capability_kind', ['prompt', 'resource', 'template', 'tool'])
async def test_publish_accepts_each_nonempty_catalog_kind(capability_kind: str) -> None:
    (connector_service, _, _, catalogs, _, publishing, _) = standard_service()
    await create_configured(connector_service)
    capabilities: dict[str, tuple[Any, ...]] = {'prompt': (DiscoveredPrompt(name='prompt', title='Prompt', description='Prompt'),), 'resource': (DiscoveredResource(name='resource', title='Resource', uri='data://resource', description='Resource'),), 'template': (DiscoveredResourceTemplate(name='template', title='Template', uri_template='data://{item}', description='Template'),), 'tool': (DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id='alpha', downstream_name='tool'), title='Tool', description='Tool', input_schema={'type': 'object'}),)}
    field_name = {'prompt': 'prompts', 'resource': 'resources', 'template': 'resource_templates', 'tool': 'tools'}[capability_kind]
    await catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='alpha', discovered_at=datetime(2026, 1, 1, tzinfo=UTC), **{'tools': (), 'prompts': (), 'resources': (), 'resource_templates': (), field_name: capabilities[capability_kind]})))
    await connector_service.publish('alpha')
    assert await publishing.is_published('alpha') is True

@pytest.mark.asyncio
async def test_publish_rejects_collision_with_native_connector_tool() -> None:
    (connector_service, _, _, catalogs, _, publishing, _) = service(ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE), EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('phase-two-secret')), ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE), ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE), (PublicToolIdentity(connector_id='native', tool_name_prefix='Alpha', operation_name='search'),))
    await create_configured(connector_service)
    await catalogs.replace(ReplaceToolCatalog(snapshot=tool_snapshot('alpha', 'search')))
    with pytest.raises(PublicToolNameConflictError):
        await connector_service.publish('alpha')
    assert await publishing.is_published('alpha') is False

@pytest.mark.asyncio
async def test_publish_rejects_empty_catalog() -> None:
    (connector_service, _, _, _, _, _, _) = standard_service()
    await create_configured(connector_service)
    with pytest.raises(DownstreamConnectorUnavailableError):
        await connector_service.publish('alpha')

@pytest.mark.asyncio
async def test_create_credential_failure_rolls_back_definition() -> None:
    credentials = FailOnceProxy(EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('phase-two-secret')), 'save')
    (connector_service, definitions, _, _, _, _, _) = service(ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE), credentials, ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE), ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE))
    with pytest.raises(RuntimeError, match='injected save failure'):
        await create_configured(connector_service)
    assert (await definitions.list()).definitions == ()

@pytest.mark.asyncio
async def test_capability_description_update_is_persisted() -> None:
    (connector_service, _, _, _, _, _, _) = standard_service()
    await create_configured(connector_service)
    updated = definition('https://example.test/mcp').model_copy(update={'capability_description': 'Search and update downstream records'})
    result = await connector_service.update(updated, '')
    assert result.capability_description == 'Search and update downstream records'
    assert await connector_service.get('alpha') == result

@pytest.mark.asyncio
async def test_same_configuration_update_preserves_valid_state_and_token() -> None:
    (connector_service, _, credentials, _, _, _, events) = standard_service()
    await create_configured(connector_service)
    await connector_service.update(definition('https://example.test/mcp'), '')
    stored = await credentials.get(ConnectorIdQuery(connector_id='alpha'))
    assert isinstance(stored, CredentialFound)
    assert isinstance(stored.credential, StaticBearerCredentialState)
    assert stored.credential.bearer_token.get_secret_value() == 'old-token'
    assert events.events == []

@pytest.mark.asyncio
async def test_published_prefix_only_update_preserves_connector_state() -> None:
    (connector_service, _, credentials, catalogs, health, publishing, events) = standard_service()
    await create_configured(connector_service)
    await catalogs.replace(ReplaceToolCatalog(snapshot=tool_snapshot('alpha', 'search')))
    await connector_service.publish('alpha')
    current_catalog = await connector_service.catalog('alpha')
    current_health = await connector_service.health('alpha')
    current_credential = await credentials.get(ConnectorIdQuery(connector_id='alpha'))
    events.events.clear()
    updated = definition('https://example.test/mcp').model_copy(update={'tool_name_prefix': 'Finance'})
    result = await connector_service.update(updated, '')
    assert result.tool_name_prefix == 'Finance'
    assert await publishing.is_published('alpha') is True
    assert await connector_service.catalog('alpha') == current_catalog
    assert await connector_service.health('alpha') == current_health
    assert await credentials.get(ConnectorIdQuery(connector_id='alpha')) == current_credential
    assert events.events == []

@pytest.mark.asyncio
async def test_published_prefix_collision_rejects_update_without_persisting() -> None:
    (connector_service, definitions, _, catalogs, _, publishing, _) = standard_service()
    await create_configured(connector_service)
    await catalogs.replace(ReplaceToolCatalog(snapshot=tool_snapshot('alpha', 'search')))
    beta = StaticBearerConnectorDefinition(connector_id='beta', display_name='Beta', tool_name_prefix='Finance', capability_description='Manage beta tools', endpoint_url='https://beta.test/mcp', public_path='/mcp/proxies/beta')
    await definitions.save(SaveConnectorDefinition(definition=beta))
    await catalogs.replace(ReplaceToolCatalog(snapshot=tool_snapshot('beta', 'search')))
    await publishing.publish_connector('alpha')
    await publishing.publish_connector('beta')
    updated = definition('https://example.test/mcp').model_copy(update={'tool_name_prefix': 'Finance'})
    with pytest.raises(PublicToolNameConflictError):
        await connector_service.update(updated, '')
    assert (await connector_service.get('alpha')).tool_name_prefix == 'Alpha'
    assert await publishing.is_published('alpha') is True

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['endpoint', 'auth', 'token'])
@pytest.mark.asyncio
async def test_configuration_changes_emit_structured_invalidation_event(change: str) -> None:
    (connector_service, _, credentials, _, _, _, events) = standard_service()
    await create_configured(connector_service)
    if change == 'endpoint':
        updated: Any = definition('https://changed.test/mcp')
        token = ''
    elif change == 'auth':
        updated = NoAuthConnectorDefinition(connector_id='alpha', display_name='Alpha', endpoint_url='https://example.test/mcp')
        token = ''
    else:
        updated = definition('https://example.test/mcp')
        token = 'new-token'
    await connector_service.update(updated, token)
    assert events.events[-1].event_type == 'connector.configuration.changed'
    stored = await credentials.get(ConnectorIdQuery(connector_id='alpha'))
    assert isinstance(stored, CredentialFound)
    if change == 'auth':
        assert isinstance(stored.credential, NoAuthCredentialState)
    elif change == 'token':
        assert isinstance(stored.credential, StaticBearerCredentialState)
        assert stored.credential.bearer_token.get_secret_value() == 'new-token'

@pytest.mark.asyncio
async def test_event_failure_after_update_does_not_restore_committed_state() -> None:
    (connector_service, definitions, credentials, _, _, _, events) = standard_service()
    await create_configured(connector_service)
    events.failure = RuntimeError('event append failed')
    with pytest.raises(RuntimeError, match='event append failed'):
        await connector_service.update(definition('https://changed.test/mcp'), 'new-token')
    persisted = await definitions.get(ConnectorIdQuery(connector_id='alpha'))
    credential = await credentials.get(ConnectorIdQuery(connector_id='alpha'))
    assert persisted.definition.endpoint_url == 'https://changed.test/mcp'
    assert isinstance(credential, CredentialFound)
    assert credential.credential.bearer_token.get_secret_value() == 'new-token'

@pytest.mark.asyncio
async def test_update_partial_failure_restores_definition_and_credential() -> None:
    health = FailOnceProxy(ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE), 'save')
    health.failed = True
    (connector_service, _, credentials, _, _, _, events) = service(ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE), EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('phase-two-secret')), ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE), health)
    await create_configured(connector_service)
    health.failed = False
    with pytest.raises(RuntimeError, match='injected save failure'):
        await connector_service.update(definition('https://changed.test/mcp'), 'new-token')
    assert await connector_service.get('alpha') == definition('https://example.test/mcp')
    stored = await credentials.get(ConnectorIdQuery(connector_id='alpha'))
    assert isinstance(stored, CredentialFound)
    assert isinstance(stored.credential, StaticBearerCredentialState)
    assert stored.credential.bearer_token.get_secret_value() == 'old-token'
    assert events.events == []

@pytest.mark.asyncio
async def test_delete_partial_failure_restores_all_already_mutated_state() -> None:
    base_catalog = ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE)
    catalogs = FailOnceProxy(base_catalog, 'delete')
    (connector_service, _, credentials, _, _, publishing, events) = service(ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE), EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('phase-two-secret')), catalogs, ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE))
    await create_configured(connector_service)
    await publishing.publish_connector('alpha')
    with pytest.raises(RuntimeError, match='injected delete failure'):
        await connector_service.delete('alpha')
    assert await connector_service.get('alpha') == definition('https://example.test/mcp')
    assert isinstance(await credentials.get(ConnectorIdQuery(connector_id='alpha')), CredentialFound)
    assert await publishing.is_published('alpha') is True
    assert events.events == []

@pytest.mark.asyncio
async def test_complete_delete_allows_clean_recreation() -> None:
    (connector_service, _, _, _, _, publishing, events) = standard_service()
    await create_configured(connector_service)
    await publishing.publish_connector('alpha')
    await connector_service.delete('alpha')
    await connector_service.create(StaticBearerCreateConnectorDefinition(display_name='Alpha', capability_description='Manage downstream tools', endpoint_url='https://example.test/mcp', public_path='/mcp/proxies/alpha', bearer_token='recreated'))
    assert await publishing.is_published('alpha') is False
    assert await publishing.was_previously_published('alpha') is False
    assert (await connector_service.catalog('alpha')).found is True
    assert (await connector_service.health('alpha')).found is True
    assert events.events[-1].metadata['state'] == 'unpublished'
