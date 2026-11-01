from umbod.core.callers import CallerContext, DeclaredIssuer
from umbod.core.identity_directory.ports import ObservedUserResolver

from ..models import Principal, PrincipalType
from .errors import PermissionDenied


class ObservedUserPrincipalResolver:
    def __init__(self, users: ObservedUserResolver) -> None:
        self._users = users

    async def resolve(self, caller: CallerContext, user_id: str) -> Principal:
        identity = await self._users.resolve(caller, user_id)
        if not isinstance(identity.issuer, DeclaredIssuer):
            raise PermissionDenied()
        return Principal(
            type=PrincipalType.USER, issuer=identity.issuer.value, id=identity.subject
        )
