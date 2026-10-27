from umbod.mcp.messaging import RuntimeProjectionSynchronizer
from messaging.models import MessagingEvent
from umbod.core.messaging import DatabaseEventStream
from umbod.core.configuration.persistence.factories import create_encrypted_connector_configuration_store
from umbod.core.configuration import ConnectorConfigurationRegistry, ConnectorConfigurationService, EnvironmentConnectorConfigurationSecret
from umbod.config.defaults import LOCAL_CONNECTOR_CONFIGURATION_SECRET
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from tests.persistence_runtime import create_inmemory_runtime
import json
from dataclasses import replace
from pathlib import Path
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from umbod.mcp.connectors.native import create_default_mcp_connector_runtime, create_default_mcp_connector_runtime_from_environment
from umbod.mcp.settings import MCPAppSettings
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from tests.support import connector_plugins as test_admin_configuration
from umbod.mcp.connectors.native.tools import InMemoryConnectorToolRuntimeStateStore
from umbod.mcp.context import PublicAppConfig
from umbod.mcp.public_app import _initialize_runtime_projection, build_starlette_app, create_runtime_context
from umbod.mcp.runtime_options import ConnectorRuntimeSourceStores, HttpConnectorRuntimeStateSourceStrategy
from umbod.core.activation import ActivationStatus, CapabilityRef
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
async def test_projection_replays_native_activation_and_advances_delivery_checkpoint() -> None:
    context = await create_runtime_context(await _default_public_app_config())
    try:
        await build_starlette_app(context)
        synchronizer = await _initialize_runtime_projection(context)
        await _configure_connector(context.mcp, 'test', True)
        await context.mcp.capability_activation_store.set_status(CapabilityRef(connector_kind='native', connector_id='test', capability_kind='tool', capability_key='echo'), ActivationStatus.ENABLED)
        stream = DatabaseEventStream(context.persistence_runtime.database)
        event = await stream.append(MessagingEvent(event_type='connector.capability_activation.changed', subject='test'))
        await synchronizer.poll_once()
        state = context.connector_tool_runtime_state_store.get_runtime_state(ConnectorToolRef(connector_id='test', operation_name='echo'))
        assert state.status == 'enabled'
        assert context.mcp.runtime_projection_health.last_applied_sequence == event.sequence
    finally:
        await context.persistence_runtime.shutdown()

@pytest.mark.asyncio
async def test_missing_api_base_url_bootstraps_durable_projection_without_http_source_options() -> None:
    context = await create_runtime_context(await _default_public_app_config())
    try:
        await build_starlette_app(context)
        synchronizer = await _initialize_runtime_projection(context)
        assert isinstance(synchronizer, RuntimeProjectionSynchronizer)
        assert context.mcp.runtime_projection_health.ready
    finally:
        await context.persistence_runtime.shutdown()


@pytest.mark.asyncio
async def test_no_api_bootstrap_preserves_explicit_host_owned_initial_configuration() -> None:
    source_configuration = InMemoryConnectorCurrentConfigurationStore()
    source_persistence = create_inmemory_runtime()
    source_publishing = ConnectorPublishingStoreService(source_persistence.database, PUBLICATION_STATE_TABLE)
    configuration = test_admin_configuration.TestConnectorAdminConfiguration(instance_name='Host source', api_key='host-key', default_response='Host response')
    await source_configuration.save_current_configuration('test', configuration)
    await source_publishing.publish_connector('test')
    config = replace(await _default_public_app_config(), source_stores=ConnectorRuntimeSourceStores(connector_configuration_store=source_configuration, connector_publishing_store=source_publishing))
    context = await create_runtime_context(config)
    try:
        await build_starlette_app(context)
        await _initialize_runtime_projection(context)
        observed = await context.target_stores.connector_configuration_store.get_current_configuration('test')
        assert observed == configuration
        assert await context.target_stores.connector_publishing_store.is_published('test')
        assert context.mcp.runtime_projection_health.ready
    finally:
        await context.persistence_runtime.shutdown()
        await source_persistence.shutdown()

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
    await _configure_connector(context.mcp, 'test', True)
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
    await _configure_connector(context.mcp, 'test', True)
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
    await _configure_connector(mcp, 'slack', True)
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
    await _configure_connector(mcp, 'slack', True)
    await mcp.connector_tool_registry.reconcile_all()
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match='Slack access is unavailable'):
            await client.call_tool('slack_read_messages', {'channel_id': 'C-PROJECT-ALPHA'})

@pytest.mark.asyncio
async def test_unpublishing_slack_runtime_state_hides_default_slack_tools() -> None:
    mcp = await build_test_mcp(None, None)
    await _configure_connector(mcp, 'slack', True)
    await mcp.connector_tool_registry.reconcile_all()
    await _configure_connector(mcp, 'slack', False)
    await mcp.connector_tool_registry.reconcile_all()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert not any((tool.name.startswith('slack_') for tool in tools))

@pytest.mark.asyncio
async def test_published_configured_test_connector_exposes_prompt_and_resource_capabilities() -> None:
    mcp = await build_test_mcp(None, None)
    await _configure_connector(mcp, 'test', True)
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

async def _configure_connector(mcp: FastMCP, connector_id: str, published: bool) -> None:
    configurations: dict[str, dict[str, str]] = {
        'test': {'instance_name': 'Local Test', 'api_key': 'test-key', 'default_response': 'Hello from test connector'},
        'slack': {'workspace_name': 'Computerlove', 'bot_token': 'xoxb-valid', 'default_channel_id': 'C-PROJECT-ALPHA'},
    }
    schema = mcp.connector_tool_registry.configuration_schema_for_connector(connector_id)
    configuration_store = ConnectorConfigurationService(registry=ConnectorConfigurationRegistry(schemas={connector_id: schema}), store=await create_encrypted_connector_configuration_store(mcp.persistence_runtime.database), secret=EnvironmentConnectorConfigurationSecret.from_value(LOCAL_CONNECTOR_CONFIGURATION_SECRET))
    publishing_store = await create_connector_publishing_store(mcp.persistence_runtime.database)
    await configuration_store.save_current_configuration(connector_id, schema.model_validate(configurations[connector_id]))
    if published:
        await publishing_store.publish_connector(connector_id)
    else:
        await publishing_store.unpublish_connector(connector_id)
