import pytest
from fastmcp import Client

from umbod.mcp.settings import MCPAppSettings, MCPSettings
from tests.umbod.mcp.connectors.test_mcp_connector_prompts_resources_acceptance import (
    RuntimeOptions,
    _configure,
    _enable_prompt_and_resource_activations,
    _prompt_mapping,
    _publish,
    _resource_mapping,
    _runtime,
)
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
)
from tests.mcp_fixtures import build_test_mcp


@pytest.mark.asyncio
async def test_gateway_mode_leaves_connector_prompts_and_resources_independently_exposed() -> None:
    runtime = _runtime(
        RuntimeOptions(
            prompt_mappings=[_prompt_mapping("knowledge_base", "summarize_article")],
            resource_mappings=[_resource_mapping("knowledge_base", "kb://articles/{article_id}")],
        )
    )
    await _configure(runtime, "knowledge_base")
    await _publish(runtime, "knowledge_base")
    settings = MCPAppSettings(
        mcp=MCPSettings(connector_tool_exposure_mode="gateway", _env_file=None),
        _env_file=None,
    )
    mcp = await build_test_mcp(settings, connector_runtime=runtime)
    await _enable_prompt_and_resource_activations(mcp, runtime)

    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        templates = await client.list_resource_templates()
        prompt = await client.get_prompt(
            "knowledge_base_summarize_article", {"article_id": "a-123"}
        )
        resource = await client.read_resource("kb://articles/a-123")

    assert "knowledge_base_summarize_article" in {item.name for item in prompts}
    assert "kb://articles/{article_id}" in {item.uri_template for item in templates}
    assert prompt.messages[0].content.text == "Summarize article a-123"
    assert resource[0].text == "Article a-123"


@pytest.mark.asyncio
async def test_connector_tool_exposure_mode_changes_only_after_server_restart() -> None:
    running_mcp = await ConnectorToolExposureMcpBuilder().build()

    async with Client(running_mcp) as client:
        before_configuration_change = {tool.name for tool in await client.list_tools()}
        setattr(running_mcp, "configured_connector_tool_exposure_mode", "gateway")
        after_configuration_change = {tool.name for tool in await client.list_tools()}

    restarted_mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    async with Client(restarted_mcp) as client:
        after_restart = {tool.name for tool in await client.list_tools()}

    assert "slack_list_readable_channels" in before_configuration_change
    assert after_configuration_change == before_configuration_change
    assert {"search_tools", "execute_tool"}.issubset(after_restart)
    assert "slack_list_readable_channels" not in after_restart
