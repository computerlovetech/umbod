from collections.abc import Mapping

from fastmcp.server.dependencies import get_access_token

from umbod.core.administrator.connector_configuration import AdministratorPrincipal


def current_administrator_principal(membership_claim: str) -> AdministratorPrincipal:
    token = get_access_token()
    claims = getattr(token, "claims", {}) if token is not None else {}
    memberships = claims.get(membership_claim, ()) if isinstance(claims, Mapping) else ()
    if isinstance(memberships, str):
        return AdministratorPrincipal(memberships=(memberships,))
    if isinstance(memberships, (list, tuple)):
        return AdministratorPrincipal(memberships=tuple(str(value) for value in memberships))
    return AdministratorPrincipal(memberships=())
