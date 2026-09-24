
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import jwt
import pytest
from fastmcp import Client, FastMCP
from pydantic import SecretStr
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.settings import MCPAppSettings, MCPSettings
from tests.support.connector_plugins import SlackAdminConfiguration
from tests.mcp_fixtures import build_test_mcp

@dataclass
class ConnectorPublishingRecord:
    connector_id: str
    published: bool

class InMemoryConnectorPublishingStore:

    def __init__(self) -> None:
        self._records: dict[str, ConnectorPublishingRecord] = {}

    async def publish_connector(self, connector_id: str) -> None:
        self._records[connector_id] = ConnectorPublishingRecord(connector_id=connector_id, published=True)

    async def is_published(self, connector_id: str) -> bool:
        record = self._records.get(connector_id)
        return record.published if record is not None else False

@dataclass
class ConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: Callable[..., dict[str, Any]]

class ConnectorToolExposureMcpBuilder:

    def __init__(self) -> None:
        self._exposure_mode = 'flat'
        self._code_execution_timeout_seconds = 30.0
        self._operation: Callable[..., dict[str, object]] = self._list_channels
        self._published = True
        self.token = jwt.encode({'email': 'engineer@example.com', 'groups': ['engineering']}, key='', algorithm='none')
        self._permissions: InMemoryGroupConnectorToolPermissions | None = None

    def in_gateway_mode(self) -> 'ConnectorToolExposureMcpBuilder':
        self._exposure_mode = 'gateway'
        return self

    def in_codemode(self) -> 'ConnectorToolExposureMcpBuilder':
        self._exposure_mode = 'codemode'
        return self

    def without_accessible_operations(self) -> 'ConnectorToolExposureMcpBuilder':
        self._published = False
        return self

    def with_operation(self, operation: Callable[..., dict[str, object]]) -> 'ConnectorToolExposureMcpBuilder':
        self._operation = operation
        return self

    def with_permissions(self, permissions: InMemoryGroupConnectorToolPermissions) -> 'ConnectorToolExposureMcpBuilder':
        self._permissions = permissions
        return self

    async def build(self) -> FastMCP:
        configuration_store = await self._configured_connector_store()
        publishing_store = InMemoryConnectorPublishingStore()
        if self._published:
            await publishing_store.publish_connector('slack')
        return await build_test_mcp(self._settings(), None, connector_registrations=[self._connector_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[self._tool_mapping()], group_permission_runtime_state=self._permissions)

    def _settings(self) -> MCPAppSettings:
        return MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode=self._exposure_mode, connector_code_execution_timeout_seconds=self._code_execution_timeout_seconds, auth_mode='single_test_user', test_bearer_token=self.token, _env_file=None), _env_file=None)

    async def _configured_connector_store(self) -> InMemoryConnectorCurrentConfigurationStore:
        store = InMemoryConnectorCurrentConfigurationStore()
        await store.save_current_configuration('slack', self._configuration())
        return store

    def _configuration(self) -> SlackAdminConfiguration:
        return SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA')

    def _connector_registration(self) -> dict[str, object]:
        return {'id': 'slack', 'display_name': 'Slack', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to Slack workspaces and channels', 'configuration_schema': SlackAdminConfiguration}

    def _tool_mapping(self) -> ConnectorToolMapping:
        return ConnectorToolMapping(connector_id='slack', operation_name='list_readable_channels', description='List Slack channels readable by the configured account.', operation=self._operation)

    def _list_channels(self) -> dict[str, object]:
        return {'channels': [{'channel_id': 'C-PROJECT-ALPHA'}]}

@pytest.mark.asyncio
async def test_default_exposure_mode_preserves_flat_connector_tools() -> None:
    mcp = await ConnectorToolExposureMcpBuilder().build()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool_names = {tool.name for tool in tools}
    assert 'slack_list_readable_channels' in tool_names
    assert 'search_tools' not in tool_names
    assert 'execute_tool' not in tool_names
    assert not {'search_openapi_capabilities', 'describe_openapi_capability', 'execute_openapi_capability'}.intersection(tool_names)

@pytest.mark.asyncio
async def test_gateway_mode_exposes_gateway_tools_instead_of_connector_tools() -> None:
    mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    assert set(tools_by_name) == {'search_tools', 'execute_tool'}
    assert 'search_tools' in tools_by_name
    assert 'execute_tool' in tools_by_name
    assert 'slack_list_readable_channels' not in tools_by_name
    assert tools_by_name['search_tools'].description == 'Search connector tools currently accessible to the authenticated user. Use connector_ids to narrow results to connector IDs represented by the capability manifest. Available connector domains: Slack: Access connector capabilities. (1 operations)'
    search_schema = tools_by_name['search_tools'].input_schema
    assert set(search_schema['required']) == {'query'}
    assert search_schema['properties']['connector_ids'] == {'default': [], 'description': 'Optional connector IDs from the capability manifest used to narrow search results.', 'items': {'type': 'string'}, 'type': 'array'}
    assert set(tools_by_name['execute_tool'].input_schema['required']) == {'tool_name', 'arguments'}
    names = [tool.name for tool in tools]
    assert 'search_openapi_capabilities' not in names
    assert 'describe_openapi_capability' not in names
    assert 'execute_openapi_capability' not in names

@pytest.mark.asyncio
async def test_codemode_exposes_unified_openapi_discovery_without_openapi_execution() -> None:
    mcp = await ConnectorToolExposureMcpBuilder().in_codemode().build()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = [tool.name for tool in tools]
    assert 'execute_code' in names
    assert names.count('search_tools') == 1
    assert 'search_openapi_capabilities' not in names
    assert 'describe_openapi_capability' not in names
    assert 'execute_openapi_capability' not in names

@pytest.mark.asyncio
async def test_gateway_search_scope_preserves_legacy_fields_and_hides_unknown_ids() -> None:
    mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    async with Client(mcp) as client:
        legacy = await client.call_tool('search_tools', {'query': 'readable channels'})
        scoped = await client.call_tool('search_tools', {'query': 'readable channels', 'connector_ids': ['unknown', 'slack']})
        denied = await client.call_tool('search_tools', {'query': 'readable channels', 'connector_ids': ['unknown']})
    assert scoped.is_error is False
    assert denied.is_error is False
    assert scoped.structured_content == legacy.structured_content
    assert denied.structured_content == {'matches': []}
    assert set(scoped.structured_content['matches'][0]) == {'tool_name', 'description', 'connector_id', 'operation_name', 'input_schema', 'relevance_score'}

@pytest.mark.asyncio
async def test_gateway_search_result_can_be_executed_by_flat_tool_name() -> None:
    received_limits: list[int] = []

    def list_readable_channels(limit: int) -> dict[str, object]:
        received_limits.append(limit)
        return {'channels': [{'channel_id': 'C-PROJECT-ALPHA'}]}
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_operation(list_readable_channels)
    mcp = await builder.build()
    (search_result, execution_result) = await _search_and_execute(mcp)
    assert search_result.is_error is False
    assert search_result.structured_content == _expected_search_content(search_result)
    assert execution_result.is_error is False
    assert execution_result.structured_content == {'channels': [{'channel_id': 'C-PROJECT-ALPHA'}]}
    assert received_limits == [5]

async def _search_and_execute(mcp: FastMCP) -> tuple[Any, Any]:
    async with Client(mcp) as client:
        search_result = await client.call_tool('search_tools', {'query': 'readable channels'})
        execution_result = await client.call_tool('execute_tool', {'tool_name': 'slack_list_readable_channels', 'arguments': {'limit': 5}})
    return (search_result, execution_result)

def _expected_search_content(search_result: Any) -> dict[str, object]:
    return {'matches': [{'tool_name': 'slack_list_readable_channels', 'description': 'List Slack channels readable by the configured account.', 'connector_id': 'slack', 'operation_name': 'list_readable_channels', 'input_schema': {'properties': {'limit': {'type': 'integer'}}, 'required': ['limit'], 'type': 'object'}, 'relevance_score': search_result.structured_content['matches'][0]['relevance_score']}]}
