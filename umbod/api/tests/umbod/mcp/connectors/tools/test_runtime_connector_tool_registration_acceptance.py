from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
import json
import re
import asyncio
from typing import Any, cast
import mcp.types
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.messages import MessageHandler
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model
from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore, RuntimeConnectorToolRegistry, register_connector_tools
from umbod.mcp.logging import McpAuditRecorder, StdoutMcpAuditEventSink, StructuredMcpAuditFormatter, create_default_mcp_tool_invocation_log_sink
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import StdoutMcpToolInvocationLogSink
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from tests.support.connector_plugins import SlackAdminConfiguration
from tests.mcp_fixtures import build_test_mcp

class GitHubAdminConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    organization: str
    api_token: SecretStr

@dataclass
class ConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: Callable[..., dict[str, Any]]
SLACK_REGISTRATION: dict[str, Any] = {'id': 'slack', 'display_name': 'Slack', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to Slack workspaces and channels', 'configuration_schema': SlackAdminConfiguration}
GITHUB_REGISTRATION: dict[str, Any] = {'id': 'github', 'display_name': 'GitHub', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to GitHub repositories and issues', 'configuration_schema': GitHubAdminConfiguration}

@pytest.mark.asyncio
async def test_connector_tool_invocation_emits_invocation_and_audit_logs() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    (invocation_stream, audit_stream) = (StringIO(), StringIO())
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    mcp = FastMCP(name='test')
    await register_connector_tools(mcp, invocation_policy=PermitAllConnectorInvocationPolicy(), connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')], tool_invocation_log_sink=StdoutMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter(), invocation_stream), audit_recorder=McpAuditRecorder(StdoutMcpAuditEventSink(StructuredMcpAuditFormatter(), audit_stream), 'test'))
    async with Client(mcp) as client:
        await client.call_tool('slack_search_messages', {})
    records = [_single_json_record(stream.getvalue()) for stream in (invocation_stream, audit_stream)]
    (invocation_record, audit_record) = records
    assert invocation_record['body'] == 'mcp tool invocation completed'
    assert audit_record['body'] == 'mcp audit event'
    assert audit_record['attributes']['mcp.audit.activity_type'] == 'tool_invocation'
    assert audit_record['attributes']['mcp.audit.outcome'] == 'success'
    assert audit_record['attributes']['mcp.tool.name'] == 'slack_search_messages'
    assert audit_record['trace_id'] == invocation_record['trace_id']

@pytest.mark.asyncio
async def test_admin_publish_makes_connector_tools_available_without_restarting_mcp_server() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')])
    async with Client(mcp) as client:
        tools_before_publish = await client.list_tools()
        await publishing_store.publish_connector('slack')
        tools_after_publish = await client.list_tools()
    assert 'slack_search_messages' not in _tool_names(tools_before_publish)
    assert 'slack_search_messages' in _tool_names(tools_after_publish)

@pytest.mark.asyncio
async def test_admin_unpublish_removes_connector_tools_without_restarting_mcp_server() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')])
    async with Client(mcp) as client:
        tools_before_unpublish = await client.list_tools()
        await publishing_store.unpublish_connector('slack')
        tools_after_unpublish = await client.list_tools()
    assert 'slack_search_messages' in _tool_names(tools_before_unpublish)
    assert 'slack_search_messages' not in _tool_names(tools_after_unpublish)

@pytest.mark.asyncio
async def test_admin_publish_exposes_all_eligible_operations_for_the_connector() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages'), _tool_mapping('slack', 'list_channels')])
    async with Client(mcp) as client:
        await publishing_store.publish_connector('slack')
        tools_after_publish = await client.list_tools()
    tool_names = _tool_names(tools_after_publish)
    assert 'slack_search_messages' in tool_names
    assert 'slack_list_channels' in tool_names
    assert all((re.fullmatch('^[a-zA-Z0-9_-]+$', tool_name) for tool_name in tool_names))

@pytest.mark.asyncio
async def test_admin_publish_of_already_published_connector_does_not_duplicate_tools() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')])
    async with Client(mcp) as client:
        await publishing_store.publish_connector('slack')
        tools_after_second_publish = await client.list_tools()
    assert _tool_names(tools_after_second_publish).count('slack_search_messages') == 1

@pytest.mark.asyncio
async def test_admin_unpublish_of_already_unpublished_connector_keeps_tools_unavailable() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')])
    async with Client(mcp) as client:
        await publishing_store.unpublish_connector('slack')
        tools_after_second_unpublish = await client.list_tools()
    assert 'slack_search_messages' not in _tool_names(tools_after_second_unpublish)

@pytest.mark.asyncio
async def test_runtime_tool_state_follows_latest_publish_state_after_rapid_changes() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')])
    async with Client(mcp) as client:
        await publishing_store.publish_connector('slack')
        await publishing_store.unpublish_connector('slack')
        tools_after_changes = await client.list_tools()
    assert 'slack_search_messages' not in _tool_names(tools_after_changes)

@pytest.mark.asyncio
async def test_unpublishing_one_connector_does_not_remove_other_connector_tools() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await _save_valid_slack_configuration(configuration_store)
    await configuration_store.save_current_configuration('github', GitHubAdminConfiguration(organization='computerlove', api_token=SecretStr('ghp-valid')))
    await publishing_store.publish_connector('slack')
    await publishing_store.publish_connector('github')
    mcp = await build_test_mcp(None, None, connector_registrations=[SLACK_REGISTRATION, GITHUB_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages'), _tool_mapping('github', 'list_issues')])
    async with Client(mcp) as client:
        await publishing_store.unpublish_connector('slack')
        tools_after_unpublish = await client.list_tools()
    tool_names = _tool_names(tools_after_unpublish)
    assert 'slack_search_messages' not in tool_names
    assert 'github_list_issues' in tool_names

@pytest.mark.asyncio
async def test_published_configured_connector_without_activation_hides_tool() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    mcp = await _build_mcp_with_runtime_state(configuration_store, publishing_store, runtime_state_store)
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert 'slack_search_messages' not in _tool_names(tools)

@pytest.mark.asyncio
async def test_enabled_activation_exposes_tool() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='enabled'))
    mcp = await _build_mcp_with_runtime_state(configuration_store, publishing_store, runtime_state_store)
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert 'slack_search_messages' in _tool_names(tools)

@pytest.mark.asyncio
async def test_disabled_activation_removes_tool() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='enabled'))
    mcp = await _build_mcp_with_runtime_state(configuration_store, publishing_store, runtime_state_store)
    registry = cast(RuntimeConnectorToolRegistry, getattr(mcp, 'connector_tool_registry'))
    async with Client(mcp, mode='legacy') as client:
        tools_before_disable = await client.list_tools()
        runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='disabled'))
        result = await registry.reconcile_runtime_state(_slack_search_messages_ref())
        tools_after_disable = await client.list_tools()
    assert 'slack_search_messages' in _tool_names(tools_before_disable)
    assert 'slack_search_messages' not in _tool_names(tools_after_disable)
    assert result.resource_name == 'slack_search_messages'
    assert result.visible_before is True
    assert result.visible_after is False
    assert result.clients_notified is True

@pytest.mark.asyncio
async def test_disabled_activation_sends_tool_list_changed_notification() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    notification_handler = RecordingToolListChangedHandler()
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='enabled'))
    mcp = await _build_mcp_with_runtime_state(configuration_store, publishing_store, runtime_state_store)
    registry = cast(RuntimeConnectorToolRegistry, getattr(mcp, 'connector_tool_registry'))
    async with Client(mcp, message_handler=notification_handler, mode='legacy') as client:
        await client.list_tools()
        runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='disabled'))
        result = await registry.reconcile_runtime_state(_slack_search_messages_ref())
        assert await notification_handler.wait_for_tool_list_changed() is True
    assert result.clients_notified is True

@pytest.mark.asyncio
async def test_enabling_after_missing_activation_adds_tool_without_publishing_change() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    await _save_valid_slack_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    mcp = await _build_mcp_with_runtime_state(configuration_store, publishing_store, runtime_state_store)
    registry = cast(RuntimeConnectorToolRegistry, getattr(mcp, 'connector_tool_registry'))
    async with Client(mcp, mode='legacy') as client:
        tools_before_enable = await client.list_tools()
        runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='enabled'))
        result = await registry.reconcile_runtime_state(_slack_search_messages_ref())
        tools_after_enable = await client.list_tools()
    assert 'slack_search_messages' not in _tool_names(tools_before_enable)
    assert 'slack_search_messages' in _tool_names(tools_after_enable)
    assert result.resource_name == 'slack_search_messages'
    assert result.visible_before is False
    assert result.visible_after is True
    assert result.clients_notified is True

@pytest.mark.asyncio
@pytest.mark.parametrize('setup_connector', ['unpublished', 'missing_configuration', 'invalid_configuration'])
async def test_enabled_activation_does_not_bypass_connector_eligibility(setup_connector: str) -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    if setup_connector == 'unpublished':
        await _save_valid_slack_configuration(configuration_store)
    if setup_connector == 'missing_configuration':
        await publishing_store.publish_connector('slack')
    if setup_connector == 'invalid_configuration':
        await publishing_store.publish_connector('slack')
        await configuration_store.save_current_configuration('slack', GitHubAdminConfiguration(organization='computerlove', api_token=SecretStr('ghp-valid')))
    runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=_slack_search_messages_ref(), status='enabled'))
    mcp = await _build_mcp_with_runtime_state(configuration_store, publishing_store, runtime_state_store)
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert 'slack_search_messages' not in _tool_names(tools)

class RecordingToolListChangedHandler(MessageHandler):

    def __init__(self) -> None:
        self._tool_list_changed = asyncio.Event()

    async def on_tool_list_changed(self, message: mcp.types.ToolListChangedNotification) -> None:
        self._tool_list_changed.set()

    async def wait_for_tool_list_changed(self) -> bool:
        try:
            await asyncio.wait_for(self._tool_list_changed.wait(), timeout=1.0)
        except TimeoutError:
            return False
        return True

async def _save_valid_slack_configuration(configuration_store: InMemoryConnectorCurrentConfigurationStore) -> None:
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))

async def _build_mcp_with_runtime_state(configuration_store: InMemoryConnectorCurrentConfigurationStore, publishing_store: ConnectorPublishingStoreService, runtime_state_store: InMemoryConnectorToolRuntimeStateStore) -> FastMCP:
    mcp = FastMCP(name='test')
    await register_connector_tools(mcp, invocation_policy=PermitAllConnectorInvocationPolicy(), connector_registrations=[SLACK_REGISTRATION], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')], connector_tool_runtime_state_store=runtime_state_store, tool_invocation_log_sink=create_default_mcp_tool_invocation_log_sink())
    return mcp

def _slack_search_messages_ref() -> ConnectorToolRef:
    return ConnectorToolRef(connector_id='slack', operation_name='search_messages')

def _tool_mapping(connector_id: str, operation_name: str) -> ConnectorToolMapping:
    return ConnectorToolMapping(connector_id=connector_id, operation_name=operation_name, description=f'Run {connector_id} {operation_name}.', operation=lambda : {'ok': True})

def _tool_names(tools: list[Any]) -> list[str]:
    return [tool.name for tool in tools]

def _single_json_record(output: str) -> dict[str, Any]:
    records = [line for line in output.splitlines() if line.strip()]
    assert len(records) == 1
    record = json.loads(records[0])
    assert isinstance(record, dict)
    return record
