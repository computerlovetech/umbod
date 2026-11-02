import logging

from collections.abc import Mapping
from typing import Any

from fastmcp.server.auth import AuthCheck
from fastmcp.server.dependencies import get_access_token, get_http_request
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.server.middleware.middleware import CallNext, MiddlewareContext

logger = logging.getLogger(__name__)

_MCP_METHODS = frozenset({
    "initialize", "ping", "tools/list", "tools/call", "prompts/list", "prompts/get",
    "resources/list", "resources/read", "resources/templates/list", "resources/subscribe",
    "resources/unsubscribe", "notifications/initialized",
})


class MCPAuthDebugMiddleware(AuthMiddleware):
    def __init__(self, *, auth: AuthCheck | list[AuthCheck], permission_group_claim: str) -> None:
        super().__init__(auth=auth)
        self._permission_group_claim = permission_group_claim

    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        self._log_auth_context(context)
        return await call_next(context)

    def _log_auth_context(self, context: MiddlewareContext[Any]) -> None:
        provider_token = get_access_token()
        claims = getattr(provider_token, "claims", {}) if provider_token is not None else {}
        logger.warning(
            "MCP authentication debug presence",
            extra={
                "mcp_method": context.method if context.method in _MCP_METHODS else "other",
                "authorization_bearer_present": _authorization_bearer_present(),
                "provider_access_token_present": provider_token is not None,
                "provider_claims_present": isinstance(claims, Mapping) and bool(claims),
                "permission_group_claim_present": isinstance(claims, Mapping)
                and self._permission_group_claim in claims,
            },
        )


def _authorization_bearer_present() -> bool:
    try:
        request = get_http_request()
    except RuntimeError:
        return False
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    return scheme.lower() == "bearer" and bool(token.strip())
