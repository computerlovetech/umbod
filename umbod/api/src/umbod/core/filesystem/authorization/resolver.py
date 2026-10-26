from umbod.core.callers import (
    AuthenticationProvenance,
    CallerSnapshot,
    DeclaredIssuer,
    SubjectIdentity,
)

from ..models import Principal, PrincipalType
from .models import ResolvedIdentity, UnresolvedIdentity


class VerifiedIdentityResolver:
    async def resolve(self, caller: CallerSnapshot) -> ResolvedIdentity | UnresolvedIdentity:
        context = caller.caller
        subject = context.subject
        if (
            context.authentication != AuthenticationProvenance.UPSTREAM_VERIFIED
            or not isinstance(subject, SubjectIdentity)
            or not isinstance(subject.issuer, DeclaredIssuer)
            or not subject.issuer.value.strip()
            or not subject.subject.strip()
            or any(not group.strip() for group in caller.groups.group_ids)
        ):
            return UnresolvedIdentity()
        issuer = subject.issuer.value
        return ResolvedIdentity(
            user=Principal(type=PrincipalType.USER, issuer=issuer, id=subject.subject),
            groups=frozenset(
                Principal(type=PrincipalType.GROUP, issuer=issuer, id=group)
                for group in caller.groups.group_ids
            ),
        )
