import asyncio
import json
import logging
from typing import Any

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.middleware.middleware import MiddlewareContext
from pytest import LogCaptureFixture, MonkeyPatch, mark
from starlette.requests import Request

from umbod.logging import OpenTelemetryJsonFormatter
from umbod.mcp.auth import debug_middleware
from umbod.mcp.auth.debug_middleware import MCPAuthDebugMiddleware


async def _call_next(_context: MiddlewareContext[Any]) -> str:
    return "ok"


@mark.parametrize("method", ["tools/list", "private-method-sentinel"])
def test_auth_debug_middleware_records_presence_without_credential_or_identity_values(
    caplog: LogCaptureFixture, monkeypatch: MonkeyPatch, method: str
) -> None:
    token = AccessToken(
        token="provider.jwt.value",
        client_id="auth0-client",
        scopes=["openid", "email"],
        claims={"email": "alex@example.com", "groups": ["workspace-admins"]},
    )
    monkeypatch.setattr(debug_middleware, "get_access_token", lambda: token)
    request = Request({
        "type": "http",
        "headers": [(b"authorization", b"Bearer request.jwt.value")],
    })
    monkeypatch.setattr(debug_middleware, "get_http_request", lambda: request)
    middleware = MCPAuthDebugMiddleware(auth=lambda _context: True, permission_group_claim="groups")
    context: MiddlewareContext[Any] = MiddlewareContext(message=object(), method=method)

    with caplog.at_level(logging.WARNING, logger="umbod.mcp.auth.debug_middleware"):
        result = asyncio.run(middleware.on_request(context, _call_next))

    assert result == "ok"
    record = caplog.records[0]
    serialized = OpenTelemetryJsonFormatter("auth-test").format(record)
    attributes = json.loads(serialized)["attributes"]
    assert attributes["mcp_method"] == (method if method == "tools/list" else "other")
    assert attributes["authorization_bearer_present"] is True
    assert attributes["provider_access_token_present"] is True
    assert attributes["provider_claims_present"] is True
    assert attributes["permission_group_claim_present"] is True
    for sensitive_value in (
        "request.jwt.value", "provider.jwt.value", "alex@example.com", "auth0-client",
        "workspace-admins", "openid", "email", "private-method-sentinel",
    ):
        assert sensitive_value not in serialized
        assert sensitive_value not in repr(record.__dict__)
        assert sensitive_value not in caplog.text


def test_auth_debug_middleware_logs_no_bearer_without_http_context(
    caplog: LogCaptureFixture, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(debug_middleware, "get_access_token", lambda: None)
    def missing_request() -> Request:
        raise RuntimeError("No HTTP context")
    monkeypatch.setattr(debug_middleware, "get_http_request", missing_request)
    middleware = MCPAuthDebugMiddleware(auth=lambda _context: True, permission_group_claim="groups")
    context: MiddlewareContext[Any] = MiddlewareContext(message=object(), method="tools/list")

    with caplog.at_level(logging.WARNING, logger="umbod.mcp.auth.debug_middleware"):
        result = asyncio.run(middleware.on_request(context, _call_next))

    assert result == "ok"
    attributes = json.loads(OpenTelemetryJsonFormatter("auth-test").format(caplog.records[0]))["attributes"]
    assert attributes["authorization_bearer_present"] is False
    assert attributes["provider_access_token_present"] is False
    assert attributes["provider_claims_present"] is False
    assert attributes["permission_group_claim_present"] is False
