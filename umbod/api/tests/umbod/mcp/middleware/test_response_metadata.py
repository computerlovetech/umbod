import asyncio
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import AuthorizationError, ToolError, ValidationError
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, CallToolResult
from fastmcp.server.middleware import MiddlewareContext

from umbod.build_identity import UMBOD_RELEASE, UMBOD_REVISION
from umbod.http_metadata import current_request_id, request_id_context
from umbod.mcp.middleware.response_metadata import McpResponseMetadataMiddleware, RESPONSE_METADATA_KEY


def metadata(result: ToolResult) -> dict[str, Any]:
    return result.meta[RESPONSE_METADATA_KEY]


@pytest.mark.asyncio
async def test_public_client_receives_additive_metadata_without_output_schema_changes() -> None:
    server = FastMCP(middleware=[McpResponseMetadataMiddleware()])

    @server.tool
    async def inspect_node(node_id: str) -> dict[str, str]:
        return {"id": node_id}

    async with Client(server) as client:
        before = (await client.list_tools())[0]
        result = await client.call_tool("inspect_node", {"node_id": "node"})
        after = (await client.list_tools())[0]

    assert result.structured_content == {"id": "node"}
    assert before.input_schema == after.input_schema
    assert before.output_schema == after.output_schema
    assert result.meta[RESPONSE_METADATA_KEY] == {
        "server_version": UMBOD_RELEASE,
        "server_revision": UMBOD_REVISION,
        "request_id": result.meta[RESPONSE_METADATA_KEY]["request_id"],
    }
    assert len(result.meta[RESPONSE_METADATA_KEY]["request_id"]) == 32
    assert current_request_id() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [ToolError, ValidationError])
async def test_raised_tool_errors_include_conversation_visible_release_and_correlation(
    error_type: type[Exception],
) -> None:
    server = FastMCP(middleware=[McpResponseMetadataMiddleware()])

    @server.tool
    async def fail() -> str:
        raise error_type("Choose an authorized destination.")

    async with Client(server) as client:
        result = await client.call_tool("fail", {}, raise_on_error=False)

    assert result.is_error
    assert result.content[0].text == "Choose an authorized destination."
    assert UMBOD_RELEASE in result.content[1].text
    assert result.meta[RESPONSE_METADATA_KEY]["request_id"] in result.content[1].text


@pytest.mark.asyncio
async def test_raw_protocol_results_preserve_content_and_metadata() -> None:
    server = FastMCP(middleware=[McpResponseMetadataMiddleware()])
    raw_result = CallToolResult.model_validate({
        "content": [{"type": "text", "text": "not available"}],
        "isError": True,
        "_meta": {"vendor": {"receipt": "retained"}},
        "structuredContent": {"code": "unavailable"},
    })
    original = raw_result.model_dump(mode="json", by_alias=True)

    @server.tool
    async def raw() -> ToolResult:
        return ToolResult.from_mcp_result(raw_result)

    result = await server.call_tool("raw", {})
    wire = result.to_mcp_result()

    assert isinstance(wire, CallToolResult)
    assert wire.is_error
    assert wire.meta["vendor"] == {"receipt": "retained"}
    assert wire.structured_content == {"code": "unavailable"}
    assert wire.content[0].text == "not available"
    assert raw_result.model_dump(mode="json", by_alias=True) == original
    assert metadata(result)["request_id"] in wire.content[1].text


@pytest.mark.asyncio
async def test_authorization_exceptions_are_not_converted_or_retried() -> None:
    middleware = McpResponseMetadataMiddleware()
    error = AuthorizationError("authorization denied")
    calls = 0

    async def denied(context: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        nonlocal calls
        calls += 1
        raise error

    context = MiddlewareContext(message=CallToolRequestParams(name="denied"), method="tools/call")
    with pytest.raises(AuthorizationError) as caught:
        await middleware.on_call_tool(context, denied)

    assert caught.value is error
    assert calls == 1
    assert current_request_id() is None


@pytest.mark.asyncio
async def test_nested_and_concurrent_calls_restore_request_context() -> None:
    server = FastMCP(middleware=[McpResponseMetadataMiddleware()])

    @server.tool
    async def inner() -> str:
        await asyncio.sleep(0)
        return "inner"

    @server.tool
    async def outer() -> ToolResult:
        before = current_request_id()
        result = await server.call_tool("inner", {})
        assert current_request_id() == before
        return result

    first, second = await asyncio.gather(server.call_tool("outer", {}), server.call_tool("outer", {}))
    assert metadata(first)["request_id"] != metadata(second)["request_id"]
    assert current_request_id() is None
    with request_id_context("http-correlation"):
        inherited = await server.call_tool("inner", {})
        assert metadata(inherited)["request_id"] == "http-correlation"
        assert current_request_id() == "http-correlation"
    assert current_request_id() is None
