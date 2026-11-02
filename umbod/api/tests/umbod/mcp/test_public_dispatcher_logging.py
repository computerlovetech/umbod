import json
import logging

import httpx
import pytest
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from umbod.logging import OpenTelemetryJsonFormatter
from umbod.mcp.connectors.downstream_mcp.runtime import (
    DownstreamDiscoverySnapshot,
    DownstreamDiscoveryUnavailable,
)
from umbod.mcp.messaging import RuntimeProjectionHealth
from umbod.mcp.public_app import DynamicPublicMcpDispatcher


class UnavailableDiscoveryRuntime:
    def capture(self) -> DownstreamDiscoverySnapshot:
        raise DownstreamDiscoveryUnavailable()

    async def reconcile(self) -> None:
        raise DownstreamDiscoveryUnavailable()


async def empty_application(scope: Scope, receive: Receive, send: Send) -> None:
    await Response(status_code=204)(scope, receive, send)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "category", "status"),
    [
        ("/mcp", "mcp", 204),
        ("/mcp/proxies/secret-canary-connector/secret-canary-tail", "proxy", 503),
        ("/secret-canary-path", "other", 204),
    ],
)
@pytest.mark.parametrize("method", ["POST", "secret-canary-method"])
@pytest.mark.parametrize("session_present", [True, False])
async def test_debug_request_logging_never_exports_request_secrets(
    path: str,
    category: str,
    status: int,
    method: str,
    session_present: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    health = RuntimeProjectionHealth()
    health.ready = True
    dispatcher = DynamicPublicMcpDispatcher(empty_application, UnavailableDiscoveryRuntime(), health)
    headers = {"Authorization": "Bearer secret-canary-authorization", "X-Private": "secret-canary-header"}
    if session_present:
        headers["MCP-Session-ID"] = "secret-canary-session"

    with caplog.at_level(logging.DEBUG, logger="umbod.mcp.public_app"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dispatcher), base_url="http://test") as client:
            response = await client.request(
                method, path, params={"token": "secret-canary-query"},
                headers=headers, content=b"secret-canary-body",
            )

    assert response.status_code == status
    records = [record for record in caplog.records if record.name == "umbod.mcp.public_app"]
    assert len(records) == 1
    serialized = OpenTelemetryJsonFormatter("test").format(records[0])
    assert "secret-canary" not in serialized
    payload = json.loads(serialized)
    assert payload["body"] == "MCP HTTP request received"
    assert payload["attributes"] == {
        "logger.name": "umbod.mcp.public_app",
        "mcp_event": "http_request",
        "mcp_http_method": "POST" if method == "POST" else "OTHER",
        "mcp_route_category": category,
        "mcp_session_present": session_present,
    }
