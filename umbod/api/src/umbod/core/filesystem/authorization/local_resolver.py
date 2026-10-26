from umbod.core.callers import AuthenticationProvenance, CallerSnapshot, DeclaredIssuer, SubjectIdentity

from ..models import Principal, PrincipalType
from .models import ResolvedIdentity, UnresolvedIdentity
from .resolver import VerifiedIdentityResolver


class LocalDevelopmentIdentityResolver:
    def __init__(self, expected_user: Principal) -> None:
        if (
            expected_user.type != PrincipalType.USER
            or not expected_user.issuer.strip()
            or not expected_user.id.strip()
        ):
            raise ValueError("A configured development user principal is required")
        self._expected_user = expected_user
        self._verified = VerifiedIdentityResolver()

    async def resolve(self, caller: CallerSnapshot) -> ResolvedIdentity | UnresolvedIdentity:
        if caller.caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED:
            return await self._verified.resolve(caller)
        subject = caller.caller.subject
        if (
            caller.caller.authentication != AuthenticationProvenance.LOCAL_SIMULATION
            or not isinstance(subject, SubjectIdentity)
            or not isinstance(subject.issuer, DeclaredIssuer)
            or subject.issuer.value != self._expected_user.issuer
            or subject.subject != self._expected_user.id
            or any(not group.strip() for group in caller.groups.group_ids)
        ):
            return UnresolvedIdentity()
        return ResolvedIdentity(
            user=self._expected_user,
            groups=frozenset(
                Principal(type=PrincipalType.GROUP, issuer=self._expected_user.issuer, id=group)
                for group in caller.groups.group_ids
            ),
        )
