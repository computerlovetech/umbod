from typing import Optional

from fastmcp.server.dependencies import get_access_token

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.identity import authenticated_personal_mcp_claims, personal_identity_facts
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalIdentityPrincipalProvider


class McpCanonicalPrincipalProvider:
    def __init__(self, settings: AppConfig) -> None:
        self._settings = settings
        self._policy = personal_identity_policy_from_app_config(settings)

    async def get_principal(self) -> Optional[CanonicalPrincipal]:
        token = get_access_token()
        if token is None:
            return None
        claims = authenticated_personal_mcp_claims(self._settings, self._policy, token.claims)
        return await PersonalIdentityPrincipalProvider(
            self._policy, personal_identity_facts(claims)
        ).get_principal()
