import asyncio
import json
from collections.abc import Callable, Awaitable
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

API_BASE_URL = "http://localhost:18010"
MCP_URL = "http://localhost:8011/mcp"
BEARER_TOKEN = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJsb2NhbC10ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3QtdXNlckBleGFtcGxlLmNvbSIsIm5hbWUiOiJMb2NhbCBUZXN0IFVzZXIiLCJncm91cHMiOlsidGVzdCJdfQ."
CONNECTOR_ID = "test"
OPERATION_NAME = "echo"
MCP_TOOL_NAME = "test_echo"
ACTIVATION_URL = f"{API_BASE_URL}/admin/connectors/catalog/{CONNECTOR_ID}/tools/activation"


@pytest.mark.asyncio
async def test_disabling_enabled_tool_removes_it_from_new_mcp_tools_list() -> None:
    _disable_tool()
    await _wait_until(_mcp_tool_is_absent)

    _enable_tool()
    await _wait_until(_mcp_tool_is_present)

    _disable_tool()

    assert await _wait_until(_mcp_tool_is_absent) is True


@pytest.mark.asyncio
async def test_disabling_enabled_tool_removes_it_from_existing_mcp_session_tools_list() -> None:
    _disable_tool()
    await _wait_until(_mcp_tool_is_absent)

    transport = StreamableHttpTransport(
        MCP_URL, headers={"Authorization": f"Bearer {BEARER_TOKEN}"}
    )
    async with Client(transport) as client:
        _enable_tool()
        assert await _wait_until(lambda: _client_tool_is_present(client)) is True

        _disable_tool()

        assert await _wait_until(lambda: _client_tool_is_absent(client)) is True


async def _mcp_tool_is_present() -> bool:
    return MCP_TOOL_NAME in await _load_mcp_tool_names()


async def _mcp_tool_is_absent() -> bool:
    return MCP_TOOL_NAME not in await _load_mcp_tool_names()


async def _client_tool_is_present(client: Client[Any]) -> bool:
    return MCP_TOOL_NAME in {tool.name for tool in await client.list_tools()}


async def _client_tool_is_absent(client: Client[Any]) -> bool:
    return MCP_TOOL_NAME not in {tool.name for tool in await client.list_tools()}


async def _wait_until(
    predicate: Callable[[], Awaitable[bool]], timeout_seconds: float = 15.0
) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(0.5)
    return await predicate()


async def _load_mcp_tool_names() -> set[str]:
    transport = StreamableHttpTransport(
        MCP_URL, headers={"Authorization": f"Bearer {BEARER_TOKEN}"}
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
    return {tool.name for tool in tools}


def _enable_tool() -> None:
    _request_json(
        "PUT",
        ACTIVATION_URL,
        {"tools": [{"tool_id": OPERATION_NAME, "activation_status": "enabled"}]},
    )


def _disable_tool() -> None:
    _request_json(
        "PUT",
        ACTIVATION_URL,
        {"tools": [{"tool_id": OPERATION_NAME, "activation_status": "disabled"}]},
    )


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        payload_text = error.read().decode("utf-8")
        raise AssertionError(f"{method} {url} failed with {error.code}: {payload_text}") from error
