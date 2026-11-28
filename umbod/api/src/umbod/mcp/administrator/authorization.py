from collections.abc import Callable

from fastmcp.utilities.authorization import AuthContext

from umbod.mcp.administrator.principal import current_administrator_claims


def administrator_authorization_check(
    membership_claim: str, required_membership: str
) -> Callable[[AuthContext], bool]:
    def check(_context: AuthContext) -> bool:
        return current_administrator_is_authorized(membership_claim, required_membership)

    return check


def current_administrator_is_authorized(membership_claim: str, required_membership: str) -> bool:
    memberships = current_administrator_claims().get(membership_claim)
    if isinstance(memberships, str):
        return memberships == required_membership
    if isinstance(memberships, (list, tuple)):
        return required_membership in memberships
    return False
