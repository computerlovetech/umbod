import logging
from typing import Any

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.middleware.middleware import MiddlewareContext
from pytest import LogCaptureFixture, MonkeyPatch

from umbod.mcp.auth import debug_middleware
from umbod.mcp.auth.debug_middleware import MCPAuthDebugMiddleware


async def _call_next(_context: MiddlewareContext[Any]) -> str:
    return "ok"


def test_auth_debug_middleware_logs_provider_token_claims(
    caplog: LogCaptureFixture, monkeypatch: MonkeyPatch
) -> None:
    token = AccessToken(
        token="provider.jwt.value",
        client_id="auth0-client",
        scopes=["openid", "email"],
        claims={"email": "alex@example.com", "groups": ["workspace-admins"]},
    )
    monkeypatch.setattr(debug_middleware, "get_access_token", lambda: token)
    monkeypatch.setattr(debug_middleware, "_authorization_bearer_jwt", lambda: "request.jwt.value")
    middleware = MCPAuthDebugMiddleware(auth=lambda _context: True, permission_group_claim="groups")
    context: MiddlewareContext[Any] = MiddlewareContext(message=object(), method="tools/list")

    with caplog.at_level(logging.WARNING, logger="umbod.mcp.auth.debug_middleware"):
        result = __import__("asyncio").run(middleware.on_request(context, _call_next))

    assert result == "ok"
    record = caplog.records[0]
    assert "request.jwt.value" in record.getMessage()
    assert "provider.jwt.value" in record.getMessage()
    assert "alex@example.com" in record.getMessage()
    assert record.authorization_bearer_jwt == "request.jwt.value"
    assert record.provider_access_token_jwt == "provider.jwt.value"
    assert record.provider_claims == {"email": "alex@example.com", "groups": ["workspace-admins"]}
    assert record.permission_group_claim == "groups"
    assert record.permission_group_claim_value == ["workspace-admins"]


def test_authorization_bearer_jwt_returns_none_without_http_context() -> None:
    assert debug_middleware._authorization_bearer_jwt() is None
