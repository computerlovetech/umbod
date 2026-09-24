from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.activation import ActivationStore, CapabilityRef, create_capability_activation_store
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, ConnectorDefinitionStoreService, ConnectorHealthStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from umbod.core.persistence import Database
from tests.persistence_runtime import create_inmemory_runtime
import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Deque
import mcp.types
import pytest
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.activation import ActivationStatus
from umbod.core.connectors.downstream_mcp.models import ConnectorHealthy, ConnectorUnhealthy, DiscoveredPrompt, DiscoveredToolWithoutOutputSchema, DiscoveryFailed, DiscoveryResult, DiscoverySucceeded, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ConnectorHealthFound, ConnectorIdQuery, ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, ToolCatalogFound
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.mcp.connectors.tools import install_tool_list_changed_notifier
from umbod.mcp.downstream_mcp_connectors import ConnectorAwareDownstreamMcpToolProvider, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.downstream_mcp_connectors.coordinator import DownstreamDiscoveryAdapters, DownstreamDiscoveryCoordinatorOptions, DownstreamDiscoveryStores, create_downstream_discovery_coordinator
from umbod.mcp.logging import McpToolInvocationCompleted
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from fastmcp import Client, FastMCP
from fastmcp.client.messages import MessageHandler
NOW = datetime(2026, 1, 2, tzinfo=UTC)

class FakeClock:

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds

class NullToolInvocationLogger:

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        return None

class RecordingNotifier:

    def __init__(self) -> None:
        self.notifications = 0
        self.prompt_notifications = 0
        self.resource_notifications = 0

    def notify_tool_list_changed(self) -> bool:
        self.notifications += 1
        return True

    def notify_prompt_list_changed(self) -> bool:
        self.prompt_notifications += 1
        return True

    def notify_resource_list_changed(self) -> bool:
        self.resource_notifications += 1
        return True

class FakeDiscovery:

    def __init__(self) -> None:
        self.results: dict[str, Deque[DiscoveryResult]] = defaultdict(deque)
        self.calls: list[str] = []
        self.active = 0
        self.maximum_active = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False

    async def discover(self, command: DiscoverDownstreamTools) -> DiscoveryResult:
        connector_id = command.definition.connector_id
        self.calls.append(connector_id)
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.started.set()
        try:
            if self.block:
                await self.release.wait()
            if self.results[connector_id]:
                return self.results[connector_id].popleft()
            return _success(connector_id, 'forecast')
        finally:
            self.active -= 1

class RecordingToolListChangedHandler(MessageHandler):

    def __init__(self) -> None:
        self.changed = asyncio.Event()

    async def on_tool_list_changed(self, message: mcp.types.ToolListChangedNotification) -> None:
        self.changed.set()

class InMemoryClientFactory:

    def __init__(self, server: FastMCP) -> None:
        self._server = server

    def create(self, command: DiscoverDownstreamTools) -> Client:
        return Client(self._server)

class CoordinatorFixture:

    def __init__(self, database: Database, activations: ActivationStore, maximum_concurrency: int=2, refresh_interval_seconds: float=10) -> None:
        self.definitions = ConnectorDefinitionStoreService(create_inmemory_runtime().database, CONNECTOR_DEFINITION_TABLE)
        self.credentials = EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('test-key'))
        self.catalogs = ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE)
        self.health = ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE)
        self.activations = activations
        self.publishing = ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
        self.discovery = FakeDiscovery()
        self.notifier = RecordingNotifier()
        self.clock = FakeClock()
        self.coordinator = create_downstream_discovery_coordinator(DownstreamDiscoveryStores(definitions=self.definitions, credentials=self.credentials, catalogs=self.catalogs, health=self.health, activations=self.activations, publishing=self.publishing), DownstreamDiscoveryAdapters(discovery=self.discovery, notifier=self.notifier, native_capabilities=self, monotonic_clock=self.clock, random_source=lambda : 1.0), DownstreamDiscoveryCoordinatorOptions(refresh_interval_seconds=refresh_interval_seconds, maximum_concurrency=maximum_concurrency, jitter_ratio=0.25, maximum_backoff_seconds=max(40, refresh_interval_seconds)))

    @classmethod
    async def create(cls, maximum_concurrency: int=2, refresh_interval_seconds: float=10) -> 'CoordinatorFixture':
        database = create_inmemory_runtime().database
        activations = await create_capability_activation_store(database)
        return cls(database, activations, maximum_concurrency, refresh_interval_seconds)

    async def native_capability_projection(self) -> tuple[tuple[object, ...], tuple[object, ...]]:
        prompts: list[object] = []
        resources: list[object] = []
        for definition in (await self.definitions.list()).definitions:
            if not await self.publishing.is_published(definition.connector_id):
                continue
            result = await self.catalogs.get(ConnectorIdQuery(connector_id=definition.connector_id))
            if not isinstance(result, ToolCatalogFound):
                continue
            prompts.extend((prompt.model_dump(mode='json') for prompt in result.snapshot.prompts))
            resources.extend((resource.model_dump(mode='json') for resource in result.snapshot.resources))
            resources.extend((template.model_dump(mode='json') for template in result.snapshot.resource_templates))
        return (tuple(sorted(prompts, key=repr)), tuple(sorted(resources, key=repr)))

    async def add(self, connector_id: str) -> None:
        await self.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id=connector_id, display_name=connector_id, endpoint_url=f'https://{connector_id}.example/mcp')))
        await self.credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id=connector_id)))

    async def expose(self, connector_id: str, operation_name: str) -> None:
        await self.publishing.publish_connector(connector_id)
        await self.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind="tool", capability_key=operation_name), ActivationStatus.ENABLED)

def _tool(connector_id: str, name: str, description: str='description') -> DiscoveredToolWithoutOutputSchema:
    return DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name=name), title=name, description=description, input_schema={'type': 'object'})

def _success(connector_id: str, *names: str) -> DiscoverySucceeded:
    return DiscoverySucceeded(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=NOW, tools=tuple((_tool(connector_id, name) for name in names))))

def _failure(connector_id: str) -> DiscoveryFailed:
    return DiscoveryFailed(connector_id=connector_id, attempted_at=NOW, reason='downstream discovery failed')

@pytest.mark.asyncio
async def test_run_refreshes_on_startup_and_periodically_until_stopped() -> None:
    fixture = await CoordinatorFixture.create(refresh_interval_seconds=0.01)
    await fixture.add('weather')
    task = asyncio.create_task(fixture.coordinator.run())
    try:
        await asyncio.wait_for(fixture.discovery.started.wait(), timeout=1)
        fixture.clock.advance(1)
        while len(fixture.discovery.calls) < 2:
            await asyncio.sleep(0.011)
        fixture.coordinator.stop()
        await asyncio.wait_for(task, timeout=1)
    finally:
        task.cancel()
    assert fixture.discovery.calls[:2] == ['weather', 'weather']

@pytest.mark.asyncio
async def test_refresh_does_not_overlap_for_same_connector() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    fixture.discovery.block = True
    first = asyncio.create_task(fixture.coordinator.refresh_connector('weather'))
    await fixture.discovery.started.wait()
    await fixture.coordinator.refresh_connector('weather')
    fixture.discovery.release.set()
    await first
    assert fixture.discovery.calls == ['weather']

@pytest.mark.asyncio
async def test_refresh_bounds_discovery_concurrency() -> None:
    fixture = await CoordinatorFixture.create(maximum_concurrency=2)
    for connector_id in ('a', 'b', 'c'):
        await fixture.add(connector_id)
    fixture.discovery.block = True
    task = asyncio.create_task(fixture.coordinator.refresh_configured_connectors(force=True))
    while fixture.discovery.maximum_active < 2:
        await asyncio.sleep(0)
    assert fixture.discovery.maximum_active == 2
    fixture.discovery.release.set()
    await task
    assert fixture.discovery.maximum_active == 2

@pytest.mark.asyncio
async def test_failures_use_exponential_backoff_with_jitter_and_reset_after_success() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    fixture.discovery.results['weather'].extend((_failure('weather'), _failure('weather'), _failure('weather'), _success('weather', 'forecast')))
    await fixture.coordinator.refresh_configured_connectors(force=True)
    fixture.clock.advance(12.4)
    await fixture.coordinator.refresh_configured_connectors(False)
    assert len(fixture.discovery.calls) == 1
    fixture.clock.advance(0.1)
    await fixture.coordinator.refresh_configured_connectors(False)
    assert len(fixture.discovery.calls) == 2
    fixture.clock.advance(24.9)
    await fixture.coordinator.refresh_configured_connectors(False)
    assert len(fixture.discovery.calls) == 2
    fixture.clock.advance(0.1)
    await fixture.coordinator.refresh_configured_connectors(False)
    fixture.clock.advance(50)
    await fixture.coordinator.refresh_configured_connectors(False)
    fixture.clock.advance(12.5)
    await fixture.coordinator.refresh_configured_connectors(False)
    assert len(fixture.discovery.calls) == 5

@pytest.mark.asyncio
async def test_run_cancels_cleanly_while_discovery_is_active() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    fixture.discovery.block = True
    task = asyncio.create_task(fixture.coordinator.run())
    await fixture.discovery.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fixture.discovery.active == 0

@pytest.mark.asyncio
async def test_success_reconciles_added_changed_removed_catalog_and_activation() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    await fixture.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(_tool('weather', 'changed', 'old'), _tool('weather', 'removed')))))
    await fixture.expose('weather', 'changed')
    await fixture.expose('weather', 'removed')
    fixture.discovery.results['weather'].append(DiscoverySucceeded(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(_tool('weather', 'added'), _tool('weather', 'changed', 'new')))))
    await fixture.coordinator.refresh_connector('weather')
    catalog = await fixture.catalogs.get(ConnectorIdQuery(connector_id='weather'))
    assert isinstance(catalog, ToolCatalogFound)
    assert [tool.identity.downstream_name for tool in catalog.snapshot.tools] == ['added', 'changed']
    assert await fixture.activations.get_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='changed')) == ActivationStatus.ENABLED
    assert await fixture.activations.get_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='removed')) == ActivationStatus.DISABLED
    assert fixture.notifier.notifications == 1

@pytest.mark.asyncio
async def test_failed_discovery_retains_last_known_good_catalog_and_activation_with_sanitized_health() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    await fixture.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(_tool('weather', 'forecast'),))))
    await fixture.expose('weather', 'forecast')
    fixture.discovery.results['weather'].append(_failure('weather'))
    await fixture.coordinator.refresh_connector('weather')
    catalog = await fixture.catalogs.get(ConnectorIdQuery(connector_id='weather'))
    health = await fixture.health.get(ConnectorIdQuery(connector_id='weather'))
    assert isinstance(catalog, ToolCatalogFound)
    assert [tool.identity.downstream_name for tool in catalog.snapshot.tools] == ['forecast']
    assert await fixture.activations.get_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='forecast')) == ActivationStatus.ENABLED
    assert isinstance(health, ConnectorHealthFound)
    assert isinstance(health.health, ConnectorUnhealthy)
    assert health.health.reason == 'downstream discovery failed'
    assert fixture.notifier.notifications == 0

@pytest.mark.asyncio
async def test_success_records_healthy_status() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    await fixture.coordinator.refresh_connector('weather')
    health = await fixture.health.get(ConnectorIdQuery(connector_id='weather'))
    assert isinstance(health, ConnectorHealthFound)
    assert isinstance(health.health, ConnectorHealthy)

@pytest.mark.asyncio
@pytest.mark.parametrize('published,enabled,expected', [(False, True, 0), (True, False, 0), (True, True, 1)])
async def test_notification_occurs_only_when_effective_exposed_tool_changes(published: bool, enabled: bool, expected: int) -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    await fixture.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(_tool('weather', 'forecast', 'old'),))))
    if published:
        await fixture.publishing.publish_connector('weather')
    if enabled:
        await fixture.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='forecast'), ActivationStatus.ENABLED)
    fixture.discovery.results['weather'].append(DiscoverySucceeded(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(_tool('weather', 'forecast', 'new'),))))
    await fixture.coordinator.refresh_connector('weather')
    assert fixture.notifier.notifications == expected

@pytest.mark.asyncio
async def test_prompt_notification_ignores_discovery_time_but_tracks_listed_metadata() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    await fixture.publishing.publish_connector('weather')
    prompt = DiscoveredPrompt(name='brief', title='Brief', description='old')
    await fixture.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(), prompts=(prompt,))))
    fixture.discovery.results['weather'].extend((DiscoverySucceeded(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=datetime(2026, 1, 3, tzinfo=UTC), tools=(), prompts=(prompt,))), DiscoverySucceeded(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=datetime(2026, 1, 4, tzinfo=UTC), tools=(), prompts=(prompt.model_copy(update={'description': 'new'}),)))))
    await fixture.coordinator.refresh_connector('weather')
    assert fixture.notifier.prompt_notifications == 0
    await fixture.coordinator.refresh_connector('weather')
    assert fixture.notifier.prompt_notifications == 1

@pytest.mark.asyncio
async def test_catalog_reconciliation_notifies_connected_session_and_updates_exposure() -> None:
    fixture = await CoordinatorFixture.create()
    await fixture.add('weather')
    await fixture.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id='weather', discovered_at=NOW, tools=(_tool('weather', 'forecast'),))))
    await fixture.expose('weather', 'forecast')
    downstream = FastMCP('downstream')

    @downstream.tool(name='alerts')
    def alerts() -> str:
        return 'alerts'
    public = FastMCP('public')
    notifier = install_tool_list_changed_notifier(public)
    public.add_provider(ConnectorAwareDownstreamMcpToolProvider(definitions=fixture.definitions, credentials=fixture.credentials, catalogs=fixture.catalogs, publishing=fixture.publishing, activations=fixture.activations, client_factory=InMemoryClientFactory(downstream), permission_policy=UnrestrictedDownstreamToolPermissionPolicy(), connector_scope='', capability_description_overrides=SystemConnectorCapabilityDescriptionOverrideStore(), tool_invocation_logger=NullToolInvocationLogger(), metrics_recorder=InMemoryMcpMetricsRecorder(), invocation_policy=PermitAllConnectorInvocationPolicy()))
    fixture.coordinator._components.native_monitor._notifier = notifier
    fixture.discovery.results['weather'].append(_success('weather', 'alerts'))
    handler = RecordingToolListChangedHandler()
    async with Client(public, message_handler=handler, mode='legacy') as client:
        assert [tool.name for tool in await client.list_tools()] == ['weather_forecast']
        assert notifier.notify_tool_list_changed() is True
        await asyncio.wait_for(handler.changed.wait(), timeout=1)
        handler.changed.clear()
        await fixture.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id='weather', capability_kind="tool", capability_key='alerts'), ActivationStatus.ENABLED)
        await fixture.coordinator.refresh_connector('weather')
        await asyncio.wait_for(handler.changed.wait(), timeout=1)
        assert [tool.name for tool in await client.list_tools()] == ['weather_alerts']
