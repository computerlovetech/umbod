import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.http import StreamableHTTPASGIApp
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from umbod.mcp.http_transport import (
    MAX_MCP_REQUEST_BODY_BYTES,
    configure_request_body_limit,
    create_mcp_http_app,
)

HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
               "clientInfo": {"name": "http-contract", "version": "1"}},
}


def rpc_result(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    if response.headers["content-type"].startswith("application/json"):
        return response.json()["result"]
    messages = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(message["result"] for message in messages if "result" in message)


@pytest.mark.parametrize("limit", [0, -1])
def test_request_body_limit_must_be_positive(limit: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        create_mcp_http_app(FastMCP(), path="/mcp", stateless_http=True, max_request_body_bytes=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("chunked", [False, True], ids=["declared", "chunked"])
async def test_oversize_http_body_is_rejected_without_tool_invocation(chunked: bool) -> None:
    invocations: list[str] = []
    server = FastMCP()

    @server.tool
    def record(value: str) -> str:
        invocations.append(value)
        return value

    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "record", "arguments": {"value": "x" * 1024}}}).encode()

    async def chunks() -> AsyncIterator[bytes]:
        for offset in range(0, len(body), 64):
            yield body[offset:offset + 64]

    app = create_mcp_http_app(server, path="/mcp", stateless_http=True, max_request_body_bytes=512)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            response = await client.post("/mcp", headers=HEADERS, content=chunks() if chunked else body)
    assert response.status_code == 413
    assert response.text == "Request body too large"
    assert ("content-length" not in response.request.headers) is chunked
    assert invocations == []


@pytest.mark.asyncio
@pytest.mark.parametrize("token,expected", [("", 401), ("bad", 401), ("good", 200)])
async def test_authentication_is_preserved(token: str, expected: int) -> None:
    server = FastMCP(auth=StaticTokenVerifier(tokens={"good": {"client_id": "test", "scopes": []}}))
    app = create_mcp_http_app(server, path="/mcp", stateless_http=True, max_request_body_bytes=4096)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            response = await client.post("/mcp", json=INITIALIZE,
                                         headers={**HEADERS, "authorization": f"Bearer {token}"})
    assert response.status_code == expected
    if expected == 200:
        assert rpc_result(response)["serverInfo"]["name"] == server.name
    else:
        assert "Bearer" in response.headers["www-authenticate"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stateless", [False, True], ids=["stateful", "stateless"])
async def test_lifespan_runs_once_and_sessions_retain_sdk_semantics(stateless: bool) -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        events.append("startup")
        try:
            yield {}
        finally:
            events.append("shutdown")

    server = FastMCP(lifespan=lifespan)
    app = create_mcp_http_app(server, path="/custom", stateless_http=stateless, max_request_body_bytes=4096)
    async with app.router.lifespan_context(app):
        assert events == ["startup"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            response = await client.post("/custom", headers=HEADERS, json=INITIALIZE)
            assert rpc_result(response)["serverInfo"]["name"] == server.name
            session_headers = dict(HEADERS)
            if stateless:
                assert "mcp-session-id" not in response.headers
            else:
                session_headers["mcp-session-id"] = response.headers["mcp-session-id"]
            initialized = await client.post("/custom", headers=session_headers,
                                            json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            assert initialized.status_code == 202
            listed = await client.post("/custom", headers=session_headers,
                                      json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            assert rpc_result(listed)["tools"] == []
        assert events == ["startup"]
    assert events == ["startup", "shutdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize("headers,expected", [
    ({"host": "evil.example"}, 421), ({"origin": "https://evil.example"}, 403),
])
async def test_configuring_limit_preserves_host_and_origin_rejection(
    headers: dict[str, str], expected: int,
) -> None:
    app = FastMCP().http_app(path="/mcp", stateless_http=True, host_origin_protection=True,
                             allowed_hosts=["localhost"], allowed_origins=["http://localhost"])
    async with app.router.lifespan_context(app):
        configure_request_body_limit(app, "/mcp", 4096)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            allowed = await client.post("/mcp", json=INITIALIZE, headers=HEADERS)
            rejected = await client.post("/mcp", json=INITIALIZE, headers={**HEADERS, **headers})
    assert allowed.status_code == 200
    assert rejected.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["missing", "duplicate", "endpoint"])
async def test_unsupported_route_layout_fails_at_startup(layout: str) -> None:
    app = create_mcp_http_app(FastMCP(), path="/mcp", stateless_http=True, max_request_body_bytes=4096)
    route = next(route for route in app.routes if isinstance(route, Route) and route.path == "/mcp")
    if layout == "missing":
        app.router.routes.remove(route)
    elif layout == "duplicate":
        app.router.routes.append(route)
    else:
        route.endpoint = PlainTextResponse("unsupported")
    with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match="Unsupported MCP HTTP")):
        async with app.router.lifespan_context(app):
            pytest.fail("Unsupported route accepted traffic")


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["manager", "limiter"])
async def test_unsupported_sdk_composition_fails_closed(layout: str) -> None:
    app = FastMCP().http_app(path="/mcp", stateless_http=True)
    async with app.router.lifespan_context(app):
        endpoint = next(route.endpoint for route in app.routes if isinstance(route, Route) and route.path == "/mcp")
        assert isinstance(endpoint, StreamableHTTPASGIApp)
        manager = endpoint.session_manager
        assert manager is not None
        if layout == "manager":
            endpoint.session_manager = object()
        else:
            manager.asgi_app = PlainTextResponse("unsupported")
        try:
            with pytest.raises(RuntimeError, match="MCP HTTP"):
                configure_request_body_limit(app, "/mcp", 4096)
        finally:
            endpoint.session_manager = manager


@pytest.mark.asyncio
async def test_forwarded_lifespan_configures_mounted_inner_app_once() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        events.append("startup")
        try:
            yield {}
        finally:
            events.append("shutdown")

    server = FastMCP(lifespan=lifespan)

    @server.tool
    def measure(value: str) -> int:
        return len(value)

    inner = create_mcp_http_app(server, path="/mcp", stateless_http=True,
                                max_request_body_bytes=6 * 1024 * 1024)
    parent = Starlette(routes=[Mount("/", app=inner)], lifespan=inner.lifespan)
    value = "x" * (4 * 1024 * 1024 + 1)
    async with parent.router.lifespan_context(parent):
        assert events == ["startup"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(parent), base_url="http://localhost") as client:
            response = await client.post("/mcp", headers=HEADERS, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "measure", "arguments": {"value": value}},
            })
        result = rpc_result(response)
        assert not result.get("isError", False)
        assert result["content"][0]["text"] == str(len(value))
        assert events == ["startup"]
    assert events == ["startup", "shutdown"]


def test_transport_cap_covers_worst_case_escaped_upload_json() -> None:
    assert MAX_MCP_REQUEST_BODY_BYTES >= 6 * 10_485_760 + 4096
