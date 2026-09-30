import asyncio
import json
from collections.abc import Callable, Awaitable
from typing import Any, Literal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from conftest import RuntimeEndpoints

CONNECTOR_ID = "test"
OPERATION_NAME = "echo"
MCP_TOOL_NAME = "test_echo"


@pytest.mark.asyncio
async def test_disabling_enabled_tool_removes_it_from_new_mcp_tools_list(runtime_endpoints: RuntimeEndpoints) -> None:
    _disable_tool(runtime_endpoints)
    assert await _wait_until(lambda: _mcp_tool_is_absent(runtime_endpoints)) is True

    _enable_tool(runtime_endpoints)
    assert await _wait_until(lambda: _mcp_tool_is_present(runtime_endpoints)) is True

    _disable_tool(runtime_endpoints)

    assert await _wait_until(lambda: _mcp_tool_is_absent(runtime_endpoints)) is True


@pytest.mark.asyncio
async def test_disabling_enabled_tool_removes_it_from_existing_mcp_session_tools_list(runtime_endpoints: RuntimeEndpoints) -> None:
    _disable_tool(runtime_endpoints)
    assert await _wait_until(lambda: _mcp_tool_is_absent(runtime_endpoints)) is True

    transport = StreamableHttpTransport(
        runtime_endpoints.mcp_url, headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    )
    async with Client(transport, mode="legacy") as client:
        assert transport.get_session_id() is not None
        _enable_tool(runtime_endpoints)
        assert await _wait_until(lambda: _client_tool_is_present(client)) is True

        _disable_tool(runtime_endpoints)

        assert await _wait_until(lambda: _client_tool_is_absent(client)) is True


@pytest.mark.asyncio
async def test_admin_mcp_write_changes_running_connector_tool_visibility(runtime_endpoints: RuntimeEndpoints) -> None:
    _disable_tool(runtime_endpoints)
    assert await _wait_until(lambda: _mcp_tool_is_absent(runtime_endpoints)) is True

    transport = StreamableHttpTransport(
        runtime_endpoints.mcp_url,
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"},
    )
    async with Client(transport) as administrator:
        await _set_admin_activation(administrator, "enabled")
        assert await _wait_until(lambda: _mcp_tool_is_present(runtime_endpoints)) is True
        await _set_admin_activation(administrator, "disabled")
        assert await _wait_until(lambda: _mcp_tool_is_absent(runtime_endpoints)) is True


async def _set_admin_activation(
    administrator: Client[Any], status: Literal["enabled", "disabled"]
) -> None:
    result = await administrator.call_tool(
        "upsert_connector_configuration",
        {
            "connector_kind": "native",
            "connector_id": CONNECTOR_ID,
            "desired_state": {
                "operations": [{
                    "operation": "set_capability_activation",
                    "capability_kind": "tool",
                    "capability_key": OPERATION_NAME,
                    "activation_status": status,
                }],
            },
        },
    )
    assert any(
        capability["capability_key"] == OPERATION_NAME
        and capability["activation_status"] == status
        for capability in result.structured_content["capabilities"]
    )


async def _mcp_tool_is_present(runtime_endpoints: RuntimeEndpoints) -> bool:
    return MCP_TOOL_NAME in await _load_mcp_tool_names(runtime_endpoints)


async def _mcp_tool_is_absent(runtime_endpoints: RuntimeEndpoints) -> bool:
    return MCP_TOOL_NAME not in await _load_mcp_tool_names(runtime_endpoints)


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


async def _load_mcp_tool_names(runtime_endpoints: RuntimeEndpoints) -> set[str]:
    transport = StreamableHttpTransport(
        runtime_endpoints.mcp_url, headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
    return {tool.name for tool in tools}


def _enable_tool(runtime_endpoints: RuntimeEndpoints) -> None:
    _request_json(
        "PUT",
        _activation_url(runtime_endpoints),
        {"tools": [{"tool_id": OPERATION_NAME, "activation_status": "enabled"}]},
    )


def _disable_tool(runtime_endpoints: RuntimeEndpoints) -> None:
    _request_json(
        "PUT",
        _activation_url(runtime_endpoints),
        {"tools": [{"tool_id": OPERATION_NAME, "activation_status": "disabled"}]},
    )


def _activation_url(runtime_endpoints: RuntimeEndpoints) -> str:
    return f"{runtime_endpoints.api_base_url}/admin/connectors/catalog/{CONNECTOR_ID}/tools/activation"


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
