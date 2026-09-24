from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
)


async def _call_search(query: str, limit: int | None = None) -> Any:
    mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    arguments: dict[str, object] = {"query": query}
    if limit is not None:
        arguments["limit"] = limit
    async with Client(mcp) as client:
        return await client.call_tool("search_tools", arguments)


@pytest.mark.asyncio
async def test_explicit_flat_mode_preserves_description_schema_and_direct_invocation() -> None:
    mcp = await ConnectorToolExposureMcpBuilder().build()
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool("slack_list_readable_channels", {})
    tool = tools["slack_list_readable_channels"]
    assert tool.description == "List Slack channels readable by the configured account."
    assert tool.input_schema["properties"] == {}
    assert tool.input_schema["type"] == "object"
    assert result.structured_content == {"channels": [{"channel_id": "C-PROJECT-ALPHA"}]}


@pytest.mark.asyncio
async def test_gateway_tools_remain_visible_without_accessible_operations() -> None:
    mcp = await (
        ConnectorToolExposureMcpBuilder().in_gateway_mode().without_accessible_operations().build()
    )
    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert {"search_tools", "execute_tool"}.issubset(names)


@pytest.mark.asyncio
async def test_search_without_accessible_matches_returns_empty_matches() -> None:
    result = await _call_search("calendar")
    assert result.structured_content == {"matches": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 51], ids=["zero", "negative", "above-maximum"])
async def test_search_rejects_limit_outside_accepted_range(limit: int) -> None:
    with pytest.raises(MCPError, match="Invalid request parameters"):
        await _call_search("messages", limit)


@pytest.mark.asyncio
async def test_search_rejects_empty_query() -> None:
    with pytest.raises(MCPError, match="Invalid request parameters"):
        await _call_search("")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [None, 3, 50], ids=["default", "custom", "maximum"])
async def test_search_honors_result_limit(limit: int | None) -> None:
    result = await _call_search("readable", limit)
    expected_limit = 10 if limit is None else limit
    assert len(result.structured_content["matches"]) <= expected_limit


@pytest.mark.asyncio
async def test_unknown_gateway_name_uses_tool_not_found_outcome() -> None:
    mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool(
                "execute_tool",
                {"tool_name": "unknown_connector_secret_operation", "arguments": {}},
            )


@pytest.mark.asyncio
async def test_execute_rejects_invalid_arguments_without_invoking_connector() -> None:
    invocations: list[int] = []

    def operation(limit: int) -> dict[str, object]:
        invocations.append(limit)
        return {"ok": True}

    mcp = (
        await ConnectorToolExposureMcpBuilder().in_gateway_mode().with_operation(operation).build()
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "execute_tool",
            {"tool_name": "slack_list_readable_channels", "arguments": {"limit": "invalid"}},
            raise_on_error=False,
        )
    assert result.is_error is True
    assert invocations == []


@pytest.mark.asyncio
async def test_connector_failure_matches_flat_and_gateway_behavior() -> None:
    def operation() -> dict[str, object]:
        raise RuntimeError("connector unavailable")

    flat = await ConnectorToolExposureMcpBuilder().with_operation(operation).build()
    gateway = (
        await ConnectorToolExposureMcpBuilder().in_gateway_mode().with_operation(operation).build()
    )
    async with Client(flat) as flat_client, Client(gateway) as gateway_client:
        with pytest.raises(ToolError) as flat_error:
            await flat_client.call_tool("slack_list_readable_channels", {})
        with pytest.raises(ToolError) as gateway_error:
            await gateway_client.call_tool(
                "execute_tool", {"tool_name": "slack_list_readable_channels", "arguments": {}}
            )
    assert str(gateway_error.value) == str(flat_error.value)


@pytest.mark.asyncio
async def test_gateway_and_flat_execution_return_equivalent_results() -> None:
    flat = await ConnectorToolExposureMcpBuilder().build()
    gateway = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    async with Client(flat) as flat_client, Client(gateway) as gateway_client:
        flat_result = await flat_client.call_tool("slack_list_readable_channels", {})
        gateway_result = await gateway_client.call_tool(
            "execute_tool", {"tool_name": "slack_list_readable_channels", "arguments": {}}
        )
    assert gateway_result.structured_content == flat_result.structured_content


@pytest.mark.asyncio
async def test_unsupported_exposure_mode_prevents_startup() -> None:
    builder = ConnectorToolExposureMcpBuilder()
    builder._exposure_mode = "hybrid"
    with pytest.raises(ValidationError):
        await builder.build()
