from collections.abc import Mapping

from fastmcp.server.dependencies import get_access_token, get_server

from umbod.core.administrator.connector_configuration import AdministratorPrincipal
from umbod.core.callers import AuthenticationProvenance
from umbod.mcp.auth.caller import authentication_provenance_for_token
from umbod.mcp.auth.groups import capture_mcp_administrator_groups


def current_administrator_principal(membership_claim: str) -> AdministratorPrincipal:
    membership = capture_mcp_administrator_groups(current_administrator_claims(), membership_claim)
    return AdministratorPrincipal(memberships=membership.group_ids)


def current_administrator_claims() -> Mapping[str, object]:
    token = get_access_token()
    if token is None:
        return {}
    try:
        provider = get_server().auth
    except RuntimeError:
        return {}
    authentication = authentication_provenance_for_token(provider, token)
    if authentication in {AuthenticationProvenance.AGENT_CREDENTIAL, AuthenticationProvenance.UNAVAILABLE}:
        return {}
    claims = getattr(token, "claims", {})
    return claims if isinstance(claims, Mapping) else {}
