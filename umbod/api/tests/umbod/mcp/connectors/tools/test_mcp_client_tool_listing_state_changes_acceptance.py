from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
import pytest
from fastmcp import Client, FastMCP
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model
from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore, RuntimeConnectorToolRegistry
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
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

class McpClientToolListingDsl:

    def __init__(self, mcp: FastMCP, publishing_store: ConnectorPublishingStoreService, runtime_state_store: InMemoryConnectorToolRuntimeStateStore) -> None:
        self.mcp = mcp
        self.publishing_store = publishing_store
        self.runtime_state_store = runtime_state_store

    async def publish_connector(self, connector_id: str) -> None:
        await self.publishing_store.publish_connector(connector_id)

    async def unpublish_connector(self, connector_id: str) -> None:
        await self.publishing_store.unpublish_connector(connector_id)

    async def enable_tool(self, connector_id: str, operation_name: str) -> None:
        await self._save_tool_status(connector_id, operation_name, 'enabled')

    async def disable_tool(self, connector_id: str, operation_name: str) -> None:
        await self._save_tool_status(connector_id, operation_name, 'disabled')

    async def reconcile_tool(self, connector_id: str, operation_name: str) -> None:
        registry = cast(RuntimeConnectorToolRegistry, getattr(self.mcp, 'connector_tool_registry'))
        await registry.reconcile_runtime_state(ConnectorToolRef(connector_id=connector_id, operation_name=operation_name))

    async def list_tool_names_from_new_client(self) -> set[str]:
        async with Client(self.mcp) as client:
            return await self.list_tool_names_from_client(client)

    async def list_tool_names_from_client(self, client: Client[Any]) -> set[str]:
        return {tool.name for tool in await client.list_tools()}

    async def _save_tool_status(self, connector_id: str, operation_name: str, status: str) -> None:
        self.runtime_state_store.save_runtime_state(ConnectorToolRuntimeState(key=ConnectorToolRef(connector_id=connector_id, operation_name=operation_name), status=status))

@pytest.mark.asyncio
async def test_runtime_tool_state_changes_are_reflected_for_existing_and_new_mcp_clients() -> None:
    dsl = await _build_published_slack_listing_dsl()
    async with Client(dsl.mcp) as existing_client:
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_client(existing_client)
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_new_client()
        await dsl.enable_tool('slack', 'search_messages')
        await dsl.reconcile_tool('slack', 'search_messages')
        assert 'slack_search_messages' in await dsl.list_tool_names_from_client(existing_client)
        assert 'slack_search_messages' in await dsl.list_tool_names_from_new_client()
        await dsl.disable_tool('slack', 'search_messages')
        await dsl.reconcile_tool('slack', 'search_messages')
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_client(existing_client)
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_new_client()

@pytest.mark.asyncio
async def test_connector_publish_state_changes_are_reflected_for_existing_and_new_mcp_clients() -> None:
    dsl = await _build_configured_slack_listing_dsl()
    await dsl.enable_tool('slack', 'search_messages')
    await dsl.reconcile_tool('slack', 'search_messages')
    async with Client(dsl.mcp) as existing_client:
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_client(existing_client)
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_new_client()
        await dsl.publish_connector('slack')
        assert 'slack_search_messages' in await dsl.list_tool_names_from_client(existing_client)
        assert 'slack_search_messages' in await dsl.list_tool_names_from_new_client()
        await dsl.unpublish_connector('slack')
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_client(existing_client)
        assert 'slack_search_messages' not in await dsl.list_tool_names_from_new_client()

@pytest.mark.asyncio
async def test_one_connector_state_change_does_not_change_other_listed_connector_tools() -> None:
    dsl = await _build_published_slack_and_github_listing_dsl()
    await _enable_and_reconcile_tool(dsl, 'slack', 'search_messages')
    await _enable_and_reconcile_tool(dsl, 'github', 'list_issues')
    async with Client(dsl.mcp) as existing_client:
        assert 'slack_search_messages' in await dsl.list_tool_names_from_client(existing_client)
        assert 'github_list_issues' in await dsl.list_tool_names_from_client(existing_client)
        await dsl.disable_tool('slack', 'search_messages')
        await dsl.reconcile_tool('slack', 'search_messages')
        existing_client_tool_names = await dsl.list_tool_names_from_client(existing_client)
        new_client_tool_names = await dsl.list_tool_names_from_new_client()
    assert 'slack_search_messages' not in existing_client_tool_names
    assert 'github_list_issues' in existing_client_tool_names
    assert 'slack_search_messages' not in new_client_tool_names
    assert 'github_list_issues' in new_client_tool_names

async def _build_published_slack_listing_dsl() -> McpClientToolListingDsl:
    dsl = await _build_configured_slack_listing_dsl()
    await dsl.publish_connector('slack')
    return dsl

async def _build_published_slack_and_github_listing_dsl() -> McpClientToolListingDsl:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    await _save_valid_slack_configuration(configuration_store)
    await _save_valid_github_configuration(configuration_store)
    await publishing_store.publish_connector('slack')
    await publishing_store.publish_connector('github')
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration(), _github_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages'), _tool_mapping('github', 'list_issues')], connector_tool_runtime_state_store=runtime_state_store)
    return McpClientToolListingDsl(mcp, publishing_store, runtime_state_store)

async def _enable_and_reconcile_tool(dsl: McpClientToolListingDsl, connector_id: str, operation_name: str) -> None:
    await dsl.enable_tool(connector_id, operation_name)
    await dsl.reconcile_tool(connector_id, operation_name)

async def _build_configured_slack_listing_dsl() -> McpClientToolListingDsl:
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    publishing_store = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    runtime_state_store = InMemoryConnectorToolRuntimeStateStore()
    await _save_valid_slack_configuration(configuration_store)
    mcp = await build_test_mcp(None, None, connector_registrations=[_slack_registration()], connector_configuration_store=configuration_store, connector_publishing_store=publishing_store, connector_tool_mappings=[_tool_mapping('slack', 'search_messages')], connector_tool_runtime_state_store=runtime_state_store)
    return McpClientToolListingDsl(mcp, publishing_store, runtime_state_store)

async def _save_valid_slack_configuration(configuration_store: InMemoryConnectorCurrentConfigurationStore) -> None:
    await configuration_store.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))

async def _save_valid_github_configuration(configuration_store: InMemoryConnectorCurrentConfigurationStore) -> None:
    await configuration_store.save_current_configuration('github', GitHubAdminConfiguration(organization='computerlove', api_token=SecretStr('ghp-valid')))

def _tool_mapping(connector_id: str, operation_name: str) -> ConnectorToolMapping:
    return ConnectorToolMapping(connector_id=connector_id, operation_name=operation_name, description=f'Run {connector_id} {operation_name}.', operation=lambda : {'ok': True})

def _slack_registration() -> dict[str, Any]:
    return {'id': 'slack', 'display_name': 'Slack', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to Slack workspaces and channels', 'configuration_schema': SlackAdminConfiguration}

def _github_registration() -> dict[str, Any]:
    return {'id': 'github', 'display_name': 'GitHub', 'capability_description': 'Access connector capabilities.', 'description': 'Connects to GitHub repositories and issues', 'configuration_schema': GitHubAdminConfiguration}
