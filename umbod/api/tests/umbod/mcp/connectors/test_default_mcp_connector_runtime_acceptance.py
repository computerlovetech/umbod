from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from tests.persistence_runtime import create_inmemory_runtime
import json
from pathlib import Path
from typing import Any
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from umbod.mcp.connectors import (
    ConnectorRuntimeState,
    ConnectorRuntimeStateSynchronizer,
    HttpConnectorRuntimeStateSynchronizationSource,
    LocalConnectorRuntimeStateSynchronizationSource,
    create_default_mcp_connector_runtime,
    create_default_mcp_connector_runtime_from_environment,
)
from umbod.mcp.settings import MCPAppSettings, PublicEndpointSettings
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from tests.support import connector_plugins as test_admin_configuration
from umbod.mcp.connectors.tools import ConnectorToolChangePollingSynchronizer, ConnectorToolRuntimeStateSynchronizer, InMemoryConnectorToolRuntimeStateStore
from umbod.mcp.context import ConnectorRuntimeStateSynchronizerOptions, PublicAppConfig
from umbod.mcp.public_app import create_connector_publication_synchronizer, create_connector_runtime_state_change_synchronizer, create_connector_runtime_state_synchronizer, create_connector_tool_change_synchronizer, create_connector_tool_runtime_state_synchronizer, create_group_permission_change_synchronizer, create_runtime_context, runtime_state_synchronizer_options
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, ConnectorStorePair, HttpConnectorRuntimeStateSourceStrategy
from umbod.mcp.live_permission_updates import GROUP_PERMISSION_CHANGE_POLL_BATCH_LIMIT, GROUP_PERMISSION_CHANGE_POLL_INTERVAL_SECONDS, GroupPermissionChangePollingSynchronizer
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.activation.events import ConnectorToolChanged, ConnectorToolChangedStreamEvent
from tests.mcp_fixtures import build_test_mcp

@pytest.fixture(autouse=True)
def UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = _write_availability_file(tmp_path, [{'id': 'slack'}, {'id': 'test'}])
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))

@pytest.mark.asyncio
async def test_default_public_mcp_has_connector_tool_registry_without_initial_connector_tools() -> None:
    config = await _default_public_app_config()
    context = await create_runtime_context(config)
    assert context.persistence_runtime is config.persistence_runtime
    assert context.mcp.persistence_runtime is config.persistence_runtime
    async with Client(context.mcp) as client:
        tools = await client.list_tools()
    assert getattr(context.mcp, 'connector_tool_registry', None) is not None
    assert context.connector_tool_runtime_state_store is not None
    assert not any((tool.name.startswith('slack_') for tool in tools))
    assert not any((tool.name.startswith('test_') for tool in tools))

@pytest.mark.asyncio
async def test_default_local_api_base_url_enables_publication_and_runtime_state_change_synchronizers() -> None:
    mcp = await build_test_mcp(None, None)
    settings = MCPAppSettings(endpoints=PublicEndpointSettings(api_base_url='http://localhost:8010'))
    options = _synchronizer_options(mcp, settings)
    api_base_url = settings.endpoints.api_base_url
    runtime_synchronizer = create_connector_runtime_state_synchronizer(options)
    downstream_coordinator = mcp.downstream_mcp_discovery_coordinator
    publication_synchronizer = create_connector_publication_synchronizer(options, api_base_url, runtime_synchronizer, downstream_coordinator)
    runtime_state_change_synchronizer = create_connector_runtime_state_change_synchronizer(options, api_base_url, runtime_synchronizer, downstream_coordinator)
    assert publication_synchronizer is not None
    assert runtime_state_change_synchronizer is not None

@pytest.mark.asyncio
async def test_tool_change_synchronizer_poll_fetches_runtime_state_reconciles_and_checkpoints() -> None:
    context = await create_runtime_context(await _default_public_app_config())
    tool = ConnectorToolRef(connector_id='test', operation_name='echo')
    state = ConnectorToolRuntimeState(key=tool, status='enabled')
    connector_synchronizer = _default_runtime_state_synchronizer(context.mcp)
    await connector_synchronizer.apply_runtime_state(_runtime_state('test'))
    runtime_synchronizer = _tool_runtime_state_synchronizer(context, state)
    synchronizer = _tool_change_synchronizer(context, runtime_synchronizer)
    await synchronizer.poll_once()
    async with Client(context.mcp) as client:
        tools = await client.list_tools()
    tool_names = {registered_tool.name for registered_tool in tools}
    checkpoint_store = synchronizer._checkpoint_store
    assert isinstance(runtime_synchronizer, ConnectorToolRuntimeStateSynchronizer)
    assert isinstance(synchronizer, ConnectorToolChangePollingSynchronizer)
    assert context.connector_tool_runtime_state_store.get_runtime_state(tool) == state
    assert 'test_echo' not in tool_names
    assert await checkpoint_store.get_last_processed_sequence('umbod-mcp-runtime-connector-tools') == 7

@pytest.mark.asyncio
async def test_missing_api_base_url_disables_runtime_state_polling() -> None:
    context = await create_runtime_context(await _default_public_app_config())
    assert runtime_state_synchronizer_options(context) is None

@pytest.mark.asyncio
async def test_default_local_api_base_url_enables_group_permission_change_synchronizer() -> None:
    context = await create_runtime_context(await _default_public_app_config())
    synchronizer = create_group_permission_change_synchronizer(context, 'http://localhost:8010', GROUP_PERMISSION_CHANGE_POLL_INTERVAL_SECONDS, GROUP_PERMISSION_CHANGE_POLL_BATCH_LIMIT)
    assert isinstance(synchronizer, GroupPermissionChangePollingSynchronizer)
    assert context.group_permission_runtime_state is not None

@pytest.mark.asyncio
async def test_explicit_source_stores_sync_into_mcp_runtime_stores_without_reader() -> None:
    mcp = await build_test_mcp(None, None)
    registry = mcp.connector_tool_registry
    source_configuration_store = InMemoryConnectorCurrentConfigurationStore()
    source_publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    source_configuration = test_admin_configuration.TestConnectorAdminConfiguration(instance_name='Source Test', api_key='test-key', default_response='Hello from source')
    await source_configuration_store.save_current_configuration('test', source_configuration)
    await source_publishing_store.publish_connector('test')
    settings = MCPAppSettings(endpoints=PublicEndpointSettings(api_base_url='http://localhost:8010'))
    source_stores = ConnectorRuntimeSourceStores(connector_configuration_store=source_configuration_store, connector_publishing_store=source_publishing_store)
    options = _synchronizer_options(mcp, settings, source_stores)
    synchronizer = create_connector_runtime_state_synchronizer(options)
    await synchronizer.sync_connector('test')
    configuration = await registry._connector_configuration_store.get_current_configuration('test')
    assert isinstance(configuration, test_admin_configuration.TestConnectorAdminConfiguration)
    assert configuration.instance_name == 'Source Test'
    assert await registry._connector_publishing_store.is_published('test') is True

@pytest.mark.asyncio
async def test_default_mcp_runtime_filters_built_ins_by_declared_ids_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability_path = _write_availability_file(tmp_path, [{'id': 'test'}, {'id': 'unknown'}, {'id': 'slack'}])
    monkeypatch.setenv('UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH', str(availability_path))
    settings = MCPAppSettings()
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    runtime = await create_default_mcp_connector_runtime_from_environment(persistence_runtime)
    assert [registration['id'] for registration in runtime.connector_registrations] == ['test', 'slack']
    assert [mapping.connector_id for mapping in runtime.connector_tool_mappings] == ['test', 'test', 'slack', 'slack', 'slack', 'slack']

@pytest.mark.asyncio
async def test_public_mcp_published_test_runtime_state_without_tool_state_hides_default_test_tools() -> None:
    context = await create_runtime_context(await _default_public_app_config())
    synchronizer = _default_runtime_state_synchronizer(context.mcp)
    await synchronizer.apply_runtime_state(_runtime_state('test'))
    await context.mcp.connector_tool_registry.reconcile_all()
    async with Client(context.mcp) as client:
        tools = await client.list_tools()
    tool_names = {tool.name for tool in tools}
    assert 'test_get_default_response' not in tool_names
    assert 'test_echo' not in tool_names

@pytest.mark.asyncio
async def test_public_mcp_enabled_tool_state_hides_enabled_tool_without_group_permission() -> None:
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=ConnectorToolRef(connector_id='test', operation_name='echo'), status='enabled'))
    context = await create_runtime_context(await _default_public_app_config(runtime_state_store))
    synchronizer = _default_runtime_state_synchronizer(context.mcp)
    await synchronizer.apply_runtime_state(_runtime_state('test'))
    await context.mcp.connector_tool_registry.reconcile_all()
    async with Client(context.mcp) as client:
        tools = await client.list_tools()
        with pytest.raises(ToolError, match='insufficient permissions'):
            await client.call_tool('test_echo', {'message': 'Hello MCP'})
    tool_names = {tool.name for tool in tools}
    assert 'test_get_default_response' not in tool_names
    assert 'test_echo' not in tool_names

@pytest.mark.asyncio
async def test_published_slack_runtime_state_makes_default_slack_tools_visible_and_callable() -> None:
    mcp = await build_test_mcp(None, None)
    synchronizer = _default_runtime_state_synchronizer(mcp)
    await synchronizer.apply_runtime_state(_runtime_state('slack'))
    await mcp.connector_tool_registry.reconcile_all()
    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool('slack_list_readable_channels', {})
    tool_names = {tool.name for tool in tools}
    assert 'slack_list_readable_channels' in tool_names
    assert 'slack_read_messages' in tool_names
    assert 'slack_read_thread' in tool_names
    assert 'slack_search_messages' in tool_names
    assert result.is_error is False
    assert result.structured_content == {'channels': [{'channel_id': 'C-PROJECT-ALPHA'}]}

@pytest.mark.asyncio
async def test_default_slack_read_messages_tool_uses_real_slack_access() -> None:
    mcp = await build_test_mcp(None, None)
    synchronizer = _default_runtime_state_synchronizer(mcp)
    await synchronizer.apply_runtime_state(_runtime_state('slack'))
    await mcp.connector_tool_registry.reconcile_all()
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match='Slack access is unavailable'):
            await client.call_tool('slack_read_messages', {'channel_id': 'C-PROJECT-ALPHA'})

@pytest.mark.asyncio
async def test_unpublishing_slack_runtime_state_hides_default_slack_tools() -> None:
    mcp = await build_test_mcp(None, None)
    synchronizer = _default_runtime_state_synchronizer(mcp)
    await synchronizer.apply_runtime_state(_runtime_state('slack'))
    await mcp.connector_tool_registry.reconcile_all()
    await synchronizer.apply_runtime_state(_runtime_state('slack', published=False))
    await mcp.connector_tool_registry.reconcile_all()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert not any((tool.name.startswith('slack_') for tool in tools))

@pytest.mark.asyncio
async def test_published_configured_test_connector_exposes_prompt_and_resource_capabilities() -> None:
    mcp = await build_test_mcp(None, None)
    synchronizer = _default_runtime_state_synchronizer(mcp)
    await synchronizer.apply_runtime_state(_runtime_state('test'))
    await mcp.capability_activation_store.set_status(
        CapabilityRef(
            connector_kind='native',
            connector_id='test',
            capability_kind='prompt',
            capability_key='test_prompt',
        ),
        ActivationStatus.ENABLED,
    )
    await mcp.capability_activation_store.set_status(
        CapabilityRef(
            connector_kind='native',
            connector_id='test',
            capability_kind='resource_template',
            capability_key='test://responses/{topic}',
        ),
        ActivationStatus.ENABLED,
    )
    await mcp.connector_prompt_registry.reconcile_all()
    await mcp.connector_resource_registry.reconcile_all()
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        prompt = await client.get_prompt('test_test_prompt', {'topic': 'greetings'})
        templates = await client.list_resource_templates()
        resources = await client.read_resource('test://responses/greetings')
    prompt_names = {listed_prompt.name for listed_prompt in prompts}
    assert 'test_test_prompt' in prompt_names
    assert 'test_prompt' not in prompt_names
    assert prompt.messages[0].content.text == 'Use Local Test to test greetings. Default response: Hello from test connector'
    assert 'test://responses/{topic}' in {template.uri_template for template in templates}
    assert resources[0].text == 'Local Test response for greetings: Hello from test connector'

def _write_availability_file(tmp_path: Path, connectors: list[dict[str, object]]) -> Path:
    path = tmp_path / 'connectors.json'
    path.write_text(json.dumps({'connectors': connectors}), encoding='utf-8')
    return path

async def _default_public_app_config(connector_tool_runtime_state_store: InMemoryConnectorToolRuntimeStateStore | None=None) -> PublicAppConfig:
    settings = MCPAppSettings()
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    await persistence_runtime.readiness.ensure_ready()
    return PublicAppConfig(settings=settings, connector_runtime=await create_default_mcp_connector_runtime(settings, persistence_runtime), source_stores=ConnectorRuntimeSourceStores(), configured_source_strategy=HttpConnectorRuntimeStateSourceStrategy(), stateless_http=False, api_base_url=None, persistence_runtime=persistence_runtime, connector_tool_runtime_state_store=connector_tool_runtime_state_store)

def _tool_runtime_state_synchronizer(context: Any, state: ConnectorToolRuntimeState) -> ConnectorToolRuntimeStateSynchronizer:
    runtime_synchronizer = create_connector_tool_runtime_state_synchronizer(context, 'http://localhost:8010')
    runtime_synchronizer._reader = _SingleToolRuntimeStateReader(state)
    return runtime_synchronizer

def _tool_change_synchronizer(
    context: Any, runtime_synchronizer: ConnectorToolRuntimeStateSynchronizer
) -> ConnectorToolChangePollingSynchronizer:
    synchronizer = create_connector_tool_change_synchronizer(
        context, 'http://localhost:8010', runtime_synchronizer
    )
    synchronizer._stream_reader = _SingleToolChangeStreamReader(
        ConnectorToolChangedStreamEvent(
            sequence=7,
            event=ConnectorToolChanged(
                connector_kind='native',
                connector_id='test',
                capability_kind='tool',
                capability_key='echo',
            ),
        )
    )
    return synchronizer

def _synchronizer_options(mcp: Any, settings: MCPAppSettings, source_stores: ConnectorRuntimeSourceStores | None=None) -> ConnectorRuntimeStateSynchronizerOptions:
    registry = mcp.connector_tool_registry
    return ConnectorRuntimeStateSynchronizerOptions(mcp=mcp, settings=settings, database=create_inmemory_runtime().database, target_stores=ConnectorStorePair(connector_configuration_store=registry._connector_configuration_store, connector_publishing_store=registry._connector_publishing_store), reader=_EmptyRuntimeStateReader(), synchronization_source=HttpConnectorRuntimeStateSynchronizationSource(_EmptyRuntimeStateReader()) if source_stores is None else LocalConnectorRuntimeStateSynchronizationSource(source_stores.connector_configuration_store, source_stores.connector_publishing_store))

def _default_runtime_state_synchronizer(mcp: Any) -> ConnectorRuntimeStateSynchronizer:
    registry = mcp.connector_tool_registry
    return ConnectorRuntimeStateSynchronizer(reader=_EmptyRuntimeStateReader(), configuration_store=registry._connector_configuration_store, publishing_store=registry._connector_publishing_store, tool_registry=registry, synchronization_source=HttpConnectorRuntimeStateSynchronizationSource(_EmptyRuntimeStateReader()))

def _runtime_state(connector_id: str, published: bool=True) -> ConnectorRuntimeState:
    configurations: dict[str, tuple[str, dict[str, str]]] = {'test': ('Test Connector', {'instance_name': 'Local Test', 'api_key': 'test-key', 'default_response': 'Hello from test connector'}), 'slack': ('Slack', {'workspace_name': 'Computerlove', 'bot_token': 'xoxb-valid', 'default_channel_id': 'C-PROJECT-ALPHA'})}
    (display_name, configuration) = configurations[connector_id]
    return ConnectorRuntimeState(connector_id=connector_id, display_name=display_name, available=True, published=published, configuration=configuration)

class _EmptyRuntimeStateReader:

    async def get_connector_runtime_state(self, connector_id: str) -> ConnectorRuntimeState | None:
        return None

    async def list_connector_runtime_states(self) -> list[ConnectorRuntimeState]:
        return []

class _SingleToolRuntimeStateReader:

    def __init__(self, state: ConnectorToolRuntimeState) -> None:
        self._state = state

    async def get_runtime_state(self, key: ConnectorToolRef) -> ConnectorToolRuntimeState | None:
        if key == self._state.key:
            return self._state
        return None

class _SingleToolChangeStreamReader:

    def __init__(self, event: ConnectorToolChangedStreamEvent) -> None:
        self._event = event

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorToolChangedStreamEvent]:
        if sequence < self._event.sequence and limit > 0:
            return [self._event]
        return []
