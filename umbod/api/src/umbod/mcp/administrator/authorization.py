from collections.abc import Callable, Mapping

from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.authorization import AuthContext


def administrator_authorization_check(
    membership_claim: str, required_membership: str
) -> Callable[[AuthContext], bool]:
    def check(_context: AuthContext) -> bool:
        token = get_access_token()
        claims = getattr(token, "claims", {}) if token is not None else {}
        if not isinstance(claims, Mapping):
            return False
        memberships = claims.get(membership_claim)
        if isinstance(memberships, str):
            return memberships == required_membership
        if isinstance(memberships, (list, tuple)):
            return required_membership in memberships
        return False

    return check
