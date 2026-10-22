from typing import Optional

from fastmcp.server.dependencies import get_access_token

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.personal_connections.development_identity import authenticated_personal_mcp_claims
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    CanonicalPrincipal,
)
from umbod.core.connectors.downstream_mcp.personal_connections import VerifiedClaimsPrincipalProvider


class McpCanonicalPrincipalProvider:
    def __init__(self, settings: AppConfig) -> None:
        self._settings = settings

    async def get_principal(self) -> Optional[CanonicalPrincipal]:
        token = get_access_token()
        if token is None:
            return None
        return await VerifiedClaimsPrincipalProvider(
            self._settings, authenticated_personal_mcp_claims(self._settings, token.claims)
        ).get_principal()
