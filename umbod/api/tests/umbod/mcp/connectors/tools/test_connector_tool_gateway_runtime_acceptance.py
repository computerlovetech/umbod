from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
import mcp.types
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.messages import MessageHandler
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore, RuntimeConnectorToolRegistry
from umbod.mcp.settings import MCPAppSettings, MCPSettings
from tests.support.connector_plugins import SlackAdminConfiguration
from tests.mcp_fixtures import build_test_mcp

class InvalidSlackConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    organization: str

@dataclass
class ConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: Callable[..., dict[str, Any]]

class RecordingToolListChangedHandler(MessageHandler):

    def __init__(self) -> None:
        self.changed = asyncio.Event()

    async def on_tool_list_changed(self, message: mcp.types.ToolListChangedNotification) -> None:
        self.changed.set()

    async def received(self) -> bool:
        try:
            await asyncio.wait_for(self.changed.wait(), timeout=0.2)
        except TimeoutError:
            return False
        return True

@dataclass
class GatewayRuntime:
    mcp: FastMCP
    configurations: InMemoryConnectorCurrentConfigurationStore
    publications: ConnectorPublishingStoreService
    activations: InMemoryConnectorToolRuntimeStateStore
    invocations: list[dict[str, Any]]

    async def reconcile(self) -> None:
        registry = cast(RuntimeConnectorToolRegistry, getattr(self.mcp, 'connector_tool_registry'))
        await registry.reconcile_runtime_state(ConnectorToolRef(connector_id='slack', operation_name='list_readable_channels'))

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['publication', 'configuration', 'activation'])
async def test_newly_eligible_tool_becomes_searchable_and_executable_at_runtime(change: str) -> None:
    runtime = await _runtime(initially_eligible=False, missing=change)
    handler = RecordingToolListChangedHandler()
    async with Client(runtime.mcp, message_handler=handler, mode='legacy') as client:
        assert await _search_names(client) == set()
        await _make_eligible(runtime, change)
        assert await _search_names(client) == {'slack_list_readable_channels'}
        result = await client.call_tool('execute_tool', {'tool_name': 'slack_list_readable_channels', 'arguments': {'limit': 5}})
        notified = await handler.received()
    assert result.is_error is False
    assert runtime.invocations == [{'limit': 5}]
    assert notified is True

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['publication', 'configuration', 'activation'])
async def test_tool_made_ineligible_disappears_and_cannot_execute_at_runtime(change: str) -> None:
    runtime = await _runtime(initially_eligible=True)
    handler = RecordingToolListChangedHandler()
    async with Client(runtime.mcp, message_handler=handler, mode='legacy') as client:
        assert await _search_names(client) == {'slack_list_readable_channels'}
        await _make_ineligible(runtime, change)
        assert await _search_names(client) == set()
        result = await client.call_tool('execute_tool', {'tool_name': 'slack_list_readable_channels', 'arguments': {'limit': 5}}, raise_on_error=False)
        notified = await handler.received()
    assert result.is_error is True
    assert runtime.invocations == []
    assert notified is True

async def _search_names(client: Client[Any]) -> set[str]:
    result = await client.call_tool('search_tools', {'query': 'readable channels'})
    return {match['tool_name'] for match in result.structured_content['matches']}

async def _runtime(initially_eligible: bool, missing: str='') -> GatewayRuntime:
    configurations = InMemoryConnectorCurrentConfigurationStore()
    publications = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    activations = InMemoryConnectorToolRuntimeStateStore()
    invocations: list[dict[str, Any]] = []
    if initially_eligible or missing != 'configuration':
        await configurations.save_current_configuration('slack', _configuration())
    if initially_eligible or missing != 'publication':
        await publications.publish_connector('slack')
    if initially_eligible or missing != 'activation':
        activations.save_runtime_state(ConnectorToolRuntimeState(key=_ref(), status='enabled'))

    def operation(limit: int) -> dict[str, Any]:
        invocations.append({'limit': limit})
        return {'channels': []}
    settings = MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode='gateway', _env_file=None), _env_file=None)
    mcp = await build_test_mcp(settings, None, connector_registrations=[{'id': 'slack', 'display_name': 'Slack', 'capability_description': 'Access connector capabilities.', 'description': 'Slack', 'configuration_schema': SlackAdminConfiguration}], connector_configuration_store=configurations, connector_publishing_store=publications, connector_tool_mappings=[ConnectorToolMapping('slack', 'list_readable_channels', 'List Slack channels readable by the configured account.', operation)], connector_tool_runtime_state_store=activations)
    return GatewayRuntime(mcp, configurations, publications, activations, invocations)

async def _make_eligible(runtime: GatewayRuntime, change: str) -> None:
    if change == 'publication':
        await runtime.publications.publish_connector('slack')
    elif change == 'configuration':
        await runtime.configurations.save_current_configuration('slack', _configuration())
        await runtime.reconcile()
    else:
        runtime.activations.save_runtime_state(ConnectorToolRuntimeState(key=_ref(), status='enabled'))
        await runtime.reconcile()

async def _make_ineligible(runtime: GatewayRuntime, change: str) -> None:
    if change == 'publication':
        await runtime.publications.unpublish_connector('slack')
    elif change == 'configuration':
        await runtime.configurations.save_current_configuration('slack', InvalidSlackConfiguration(organization='computerlove'))
        await runtime.reconcile()
    else:
        runtime.activations.save_runtime_state(ConnectorToolRuntimeState(key=_ref(), status='disabled'))
        await runtime.reconcile()

def _configuration() -> SlackAdminConfiguration:
    return SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA')

def _ref() -> ConnectorToolRef:
    return ConnectorToolRef(connector_id='slack', operation_name='list_readable_channels')
