import pytest
from fastmcp import Client

from tests.mcp_fixtures import build_test_mcp
from tests.persistence_runtime import create_inmemory_runtime
from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.agent_instructions import AGENT_INSTRUCTIONS, AGENT_INSTRUCTIONS_URI
from umbod.mcp.settings import MCPAppSettings, MCPSettings


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["flat", "gateway", "codemode"])
async def test_setup_resource_available_without_connectors_or_permissions(mode):
    mcp = await build_test_mcp(
        MCPAppSettings(
            mcp=MCPSettings(connector_tool_exposure_mode=mode, downstream_discovery_enabled=False),
            _env_file=None,
        ),
        connector_runtime=ConnectorRuntime(
            connector_registrations=[],
            connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(),
            connector_publishing_store=ConnectorPublishingStoreService(
                create_inmemory_runtime().database, PUBLICATION_STATE_TABLE
            ),
            connector_tool_mappings=[],
        ),
        group_permission_runtime_state=InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",)),
    )
    async with Client(mcp) as client:
        resources = await client.list_resources()
        resource = next(item for item in resources if str(item.uri) == AGENT_INSTRUCTIONS_URI)
        assert resource.mime_type == "text/markdown"
        contents = await client.read_resource(AGENT_INSTRUCTIONS_URI)
        assert contents[0].text == AGENT_INSTRUCTIONS
        assert "<!-- umbod:begin -->" in contents[0].text
        assert not any(prompt.name == "setup_umbod" for prompt in await client.list_prompts())
        assert not any(tool.name == "setup_umbod" for tool in await client.list_tools())
