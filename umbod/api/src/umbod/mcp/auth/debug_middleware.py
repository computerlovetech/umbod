import json
import logging

from collections.abc import Mapping
from typing import Any

from fastmcp.server.auth import AuthCheck
from fastmcp.server.dependencies import get_access_token, get_http_request
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.server.middleware.middleware import CallNext, MiddlewareContext

logger = logging.getLogger(__name__)


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
        payload = {
            "mcp_method": context.method,
            "authorization_bearer_jwt": _authorization_bearer_jwt(),
            "provider_access_token_jwt": getattr(provider_token, "token", None),
            "provider_client_id": getattr(provider_token, "client_id", None),
            "provider_scopes": getattr(provider_token, "scopes", None),
            "provider_expires_at": getattr(provider_token, "expires_at", None),
            "provider_resource": getattr(provider_token, "resource", None),
            "provider_claims": claims if isinstance(claims, Mapping) else {},
            "permission_group_claim": self._permission_group_claim,
            "permission_group_claim_value": claims.get(self._permission_group_claim)
            if isinstance(claims, Mapping)
            else None,
        }
        logger.warning(
            "MCP auth debug context %s",
            json.dumps(payload, default=str, sort_keys=True),
            extra=payload,
        )


def _authorization_bearer_jwt() -> str | None:
    try:
        request = get_http_request()
    except RuntimeError:
        return None
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
