from typing import Any, Optional

import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from conftest import RuntimeEndpoints


@pytest.mark.asyncio
async def test_stateful_runtime_issues_and_reuses_session_id(runtime_endpoints: RuntimeEndpoints) -> None:
    request_session_ids: list[Optional[str]] = []
    response_session_ids: list[Optional[str]] = []

    async def record_request(request: httpx2.Request) -> None:
        request_session_ids.append(request.headers.get("mcp-session-id"))

    async def record_response(response: httpx2.Response) -> None:
        response_session_ids.append(response.headers.get("mcp-session-id"))

    def create_http_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            event_hooks={"request": [record_request], "response": [record_response]},
            **kwargs,
        )

    transport = StreamableHttpTransport(
        runtime_endpoints.mcp_url,
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"},
        httpx_client_factory=create_http_client,
    )
    async with Client(transport) as client:
        await client.list_tools()
        session_id = transport.get_session_id()
        await client.list_prompts()

    assert session_id is not None
    assert session_id in response_session_ids
    assert request_session_ids[0] is None
    assert session_id in request_session_ids[1:]


@pytest.mark.asyncio
async def test_stateful_runtime_rejects_unknown_session_id(runtime_endpoints: RuntimeEndpoints) -> None:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {runtime_endpoints.bearer_token}",
        "Content-Type": "application/json",
        "Mcp-Session-Id": "unknown-session-id",
    }
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }

    async with httpx2.AsyncClient() as client:
        response = await client.post(runtime_endpoints.mcp_url, headers=headers, json=request)

    assert response.status_code == 404
    assert response.headers.get("mcp-session-id") is None
