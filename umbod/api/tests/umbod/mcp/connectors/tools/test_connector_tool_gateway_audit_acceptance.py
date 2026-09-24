from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from tests.persistence_runtime import create_inmemory_runtime
import json
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from typing import Any
import pytest
from fastmcp import Client, FastMCP
from pydantic import SecretStr
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.tools import register_connector_tools
from umbod.mcp.logging import McpAuditIdentityAdapter, McpAuditRecorder, StdoutMcpAuditEventSink, StructuredMcpAuditFormatter, create_default_mcp_tool_invocation_log_sink
from umbod.mcp.middleware import McpAuditMiddleware
from tests.support.connector_plugins import SlackAdminConfiguration

@dataclass
class ConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: Callable[..., dict[str, Any]]

@pytest.mark.asyncio
async def test_gateway_execution_audits_outer_and_resolved_connector_identities() -> None:
    (mcp, audit_stream) = await _audited_gateway()
    async with Client(mcp) as client:
        await client.call_tool('execute_tool', {'tool_name': 'slack_list_readable_channels', 'arguments': {'limit': 5}})
    records = _records(audit_stream)
    assert {record['attributes']['mcp.tool.name'] for record in records} == {'execute_tool', 'slack_list_readable_channels'}
    resolved = next((record['attributes'] for record in records if record['attributes']['mcp.tool.name'] == 'slack_list_readable_channels'))
    assert resolved['mcp.connector.id'] == 'slack'
    assert resolved['mcp.operation.name'] == 'list_readable_channels'
    assert all((record['attributes']['mcp.audit.activity_type'] == 'tool_invocation' for record in records))

@pytest.mark.asyncio
async def test_gateway_search_is_audit_visible_as_search_tools_invocation() -> None:
    (mcp, audit_stream) = await _audited_gateway()
    async with Client(mcp) as client:
        await client.call_tool('search_tools', {'query': 'channels'})
    records = _records(audit_stream)
    assert len(records) == 1
    assert records[0]['attributes']['mcp.audit.activity_type'] == 'tool_invocation'
    assert records[0]['attributes']['mcp.tool.name'] == 'search_tools'
    assert records[0]['attributes']['mcp.audit.outcome'] == 'success'

async def _audited_gateway() -> tuple[FastMCP, StringIO]:
    configurations = InMemoryConnectorCurrentConfigurationStore()
    await configurations.save_current_configuration('slack', SlackAdminConfiguration(workspace_name='Computerlove', bot_token=SecretStr('xoxb-valid'), default_channel_id='C-PROJECT-ALPHA'))
    publications = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await publications.publish_connector('slack')
    stream = StringIO()
    audit_recorder = McpAuditRecorder(StdoutMcpAuditEventSink(StructuredMcpAuditFormatter(), stream), 'test')
    mcp = FastMCP(name='test', middleware=[McpAuditMiddleware(audit_recorder, McpAuditIdentityAdapter(), exposure_mode='gateway')])
    await register_connector_tools(mcp, invocation_policy=PermitAllConnectorInvocationPolicy(), connector_registrations=[{'id': 'slack', 'display_name': 'Slack', 'capability_description': 'Access connector capabilities.', 'description': 'Slack', 'configuration_schema': SlackAdminConfiguration}], connector_configuration_store=configurations, connector_publishing_store=publications, connector_tool_mappings=[ConnectorToolMapping('slack', 'list_readable_channels', 'List Slack channels.', lambda limit: {'channels': []})], connector_tool_exposure_mode='gateway', tool_invocation_log_sink=create_default_mcp_tool_invocation_log_sink(), audit_recorder=audit_recorder)
    return (mcp, stream)

def _records(stream: StringIO) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    return [record for record in records if record['attributes']['mcp.audit.activity_type'] == 'tool_invocation']
