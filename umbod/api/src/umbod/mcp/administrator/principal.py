from collections.abc import Mapping

from fastmcp.server.dependencies import get_access_token

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.mcp.auth.groups import capture_mcp_administrator_groups


def current_administrator_principal(membership_claim: str) -> AdministratorPrincipal:
    token = get_access_token()
    claims = getattr(token, "claims", {}) if token is not None else {}
    if not isinstance(claims, Mapping):
        return AdministratorPrincipal(memberships=())
    membership = capture_mcp_administrator_groups(claims, membership_claim)
    return AdministratorPrincipal(memberships=membership.group_ids)
