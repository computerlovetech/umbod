
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import pytest
from fastmcp import Client
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from tests.support.connector_plugins import SlackAdminConfiguration
from tests.mcp_fixtures import build_test_mcp

class GitHubAdminConfiguration(Model):
    model_config = ConfigDict(extra='forbid')
    organization: str
    api_token: SecretStr

@dataclass
class ConnectorPublishingRecord:
    connector_id: str
    published: bool

class InMemoryConnectorPublishingStore:

    def __init__(self) -> None:
        self._records: dict[str, ConnectorPublishingRecord] = {}

    async def publish_connector(self, connector_id: str) -> None:
        self._records[connector_id] = ConnectorPublishingRecord(connector_id=connector_id, published=True)

    async def unpublish_connector(self, connector_id: str) -> None:
        self._records[connector_id] = ConnectorPublishingRecord(connector_id=connector_id, published=False)

    async def is_published(self, connector_id: str) -> bool:
        record = self._records.get(connector_id)
        return record.published if record is not None else False

@dataclass
class ConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: Callable[..., dict[str, Any]]

@pytest.mark.asyncio
async def test_published_configured_connector_is_listed_as_mcp_tools() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = InMemoryConnectorPublishingStore()
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))
    await publishing_store.publish_connector('slack')
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[ConnectorToolMapping(connector_id='slack', operation_name='list_readable_channels', description='List readable Slack channels.', operation=lambda : {'channels': [{'channel_id': 'C-PROJECT-ALPHA'}]}), ConnectorToolMapping(connector_id='slack', operation_name='read_messages', description='Read Slack channel messages.', operation=lambda channel_id: {'channel_id': channel_id, 'messages': []})])
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool_names = {tool.name for tool in tools}
    assert 'slack_list_readable_channels' in tool_names
    assert 'slack_read_messages' in tool_names

@pytest.mark.asyncio
async def test_mcp_client_invokes_a_listed_connector_tool_and_receives_tool_result() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = InMemoryConnectorPublishingStore()
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))
    await publishing_store.publish_connector('slack')
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[ConnectorToolMapping(connector_id='slack', operation_name='read_messages', description='Read Slack channel messages.', operation=lambda channel_id: {'channel_id': channel_id, 'messages': [{'text': 'Launch update is ready'}]})])
    async with Client(mcp) as client:
        result = await client.call_tool('slack_read_messages', {'channel_id': 'C-PROJECT-ALPHA'})
    assert result.is_error is False
    assert result.structured_content == {'channel_id': 'C-PROJECT-ALPHA', 'messages': [{'text': 'Launch update is ready'}]}
    assert result.meta is not None
    assert result.meta['connector_id'] == 'slack'
    assert result.meta['operation_name'] == 'read_messages'

@pytest.mark.asyncio
async def test_mcp_tool_list_hides_connectors_that_are_unpublished_unconfigured_invalid_or_unavailable() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = InMemoryConnectorPublishingStore()
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))
    await configuration_store.save_current_configuration('github', GitHubAdminConfiguration(organization='computerlove', api_token=SecretStr('ghp-valid')))
    await configuration_store.save_current_configuration('unavailable', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-UNAVAILABLE'))
    await publishing_store.publish_connector('github')
    await publishing_store.publish_connector('unconfigured')
    await publishing_store.publish_connector('unavailable')
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration(), _github_registration(), _unconfigured_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[ConnectorToolMapping('slack', 'read_messages', 'Read Slack channel messages.', lambda channel_id: {'channel_id': channel_id}), ConnectorToolMapping('github', 'list_issues', 'List GitHub issues.', lambda : {'issues': []}), ConnectorToolMapping('unconfigured', 'read', 'Read unconfigured data.', lambda : {'items': []}), ConnectorToolMapping('unavailable', 'read', 'Read unavailable data.', lambda : {'items': []})])
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool_names = {tool.name for tool in tools}
    assert 'github_list_issues' in tool_names
    assert 'slack_read_messages' not in tool_names
    assert 'unconfigured_read' not in tool_names
    assert 'unavailable_read' not in tool_names

@pytest.mark.asyncio
async def test_connector_tool_mapping_lists_only_mapped_operations_for_each_connector() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = InMemoryConnectorPublishingStore()
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))
    await configuration_store.save_current_configuration('github', GitHubAdminConfiguration(organization='computerlove', api_token=SecretStr('ghp-valid')))
    await publishing_store.publish_connector('slack')
    await publishing_store.publish_connector('github')
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration(), _github_registration(), _acme_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[ConnectorToolMapping('slack', 'list_readable_channels', 'List readable Slack channels.', lambda : {'channels': []}), ConnectorToolMapping('slack', 'read_messages', 'Read Slack channel messages.', lambda channel_id: {'channel_id': channel_id}), ConnectorToolMapping('github', 'list_issues', 'List GitHub issues.', lambda : {'issues': []})])
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool_names = {tool.name for tool in tools}
    assert 'slack_list_readable_channels' in tool_names
    assert 'slack_read_messages' in tool_names
    assert 'slack_send_messages' not in tool_names
    assert 'github_list_issues' in tool_names
    assert not any((tool_name.startswith('acme_') for tool_name in tool_names))

@pytest.mark.asyncio
async def test_connector_tool_failures_return_instructive_tool_results_without_hiding_other_tools() -> None:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = InMemoryConnectorPublishingStore()
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))
    await publishing_store.publish_connector('slack')

    def unavailable_operation(channel_id: str) -> dict[str, Any]:
        raise RuntimeError(f'Slack channel is not readable: {channel_id}')
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[ConnectorToolMapping('slack', 'read_messages', 'Read Slack channel messages.', unavailable_operation), ConnectorToolMapping('slack', 'list_readable_channels', 'List readable Slack channels.', lambda : {'channels': []})])
    async with Client(mcp) as client:
        result = await client.call_tool('slack_read_messages', {'channel_id': 'C-PRIVATE'}, raise_on_error=False)
        tools_after_failure = await client.list_tools()
    assert result.is_error is True
    assert result.content[0].text == 'The Slack read_messages tool could not complete: Slack channel is not readable: C-PRIVATE'
    assert 'slack_list_readable_channels' in {tool.name for tool in tools_after_failure}

def _slack_registration() -> dict[str, Any]:
    return {'id': 'slack', 'display_name': 'Slack', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to Slack workspaces and channels', 'configuration_schema': SlackAdminConfiguration}

def _github_registration() -> dict[str, Any]:
    return {'id': 'github', 'display_name': 'GitHub', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to GitHub repositories and issues', 'configuration_schema': GitHubAdminConfiguration}

def _unconfigured_registration() -> dict[str, Any]:
    return {'id': 'unconfigured', 'display_name': 'Unconfigured', 'capability_description': 'Access connector capabilities.', 'description': 'Connector without a current configuration', 'configuration_schema': SlackAdminConfiguration}

def _acme_registration() -> dict[str, Any]:
    return {'id': 'acme', 'display_name': 'Acme', 'capability_description': 'Access connector capabilities.', 'description': 'Connector without mapped operations', 'configuration_schema': SlackAdminConfiguration}
