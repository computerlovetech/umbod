from umbod.core.callers import (
    LOCAL_DEVELOPMENT_ISSUER,
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)

from .errors import UntrustedPersonalAccessTokenCaller
from .models import TokenOwner


class VerifiedPersonalAccessTokenOwnerResolver:
    def resolve(self, caller: CallerContext) -> TokenOwner:
        if not isinstance(caller, CallerContext):
            raise UntrustedPersonalAccessTokenCaller()
        subject = caller.subject
        if (
            caller.authentication != AuthenticationProvenance.UPSTREAM_VERIFIED
            or not isinstance(subject, SubjectIdentity)
            or not isinstance(subject.issuer, DeclaredIssuer)
            or not subject.issuer.value.strip()
            or not subject.subject.strip()
        ):
            raise UntrustedPersonalAccessTokenCaller()
        return TokenOwner(issuer=subject.issuer.value, subject=subject.subject)


class LocalDevelopmentPersonalAccessTokenOwnerResolver:
    def __init__(self, simulated_subject: str) -> None:
        if not simulated_subject.strip():
            raise ValueError("A configured development user subject is required")
        self._simulated_subject = simulated_subject
        self._verified = VerifiedPersonalAccessTokenOwnerResolver()

    def resolve(self, caller: CallerContext) -> TokenOwner:
        if not isinstance(caller, CallerContext):
            raise UntrustedPersonalAccessTokenCaller()
        if caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED:
            return self._verified.resolve(caller)
        subject = caller.subject
        if (
            caller.authentication != AuthenticationProvenance.LOCAL_SIMULATION
            or not isinstance(subject, SubjectIdentity)
            or not isinstance(subject.issuer, DeclaredIssuer)
            or subject.issuer.value != LOCAL_DEVELOPMENT_ISSUER
            or subject.subject != self._simulated_subject
        ):
            raise UntrustedPersonalAccessTokenCaller()
        return TokenOwner(issuer=subject.issuer.value, subject=subject.subject)
