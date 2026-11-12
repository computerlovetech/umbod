from fastmcp.server.auth.providers.google import GoogleProvider

from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableIssuer
from umbod.core.usage import UsageOwnership, resolve_usage_owner


_GOOGLE_ISSUERS = frozenset({'https://accounts.google.com', 'accounts.google.com'})


def resolve_mcp_usage_owner(caller: CallerContext, provider: object, configured_issuer: str) -> UsageOwnership:
    subject = caller.subject
    if (
        type(provider) is GoogleProvider
        and caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED
        and isinstance(subject, SubjectIdentity)
        and isinstance(subject.issuer, UnavailableIssuer)
        and configured_issuer in _GOOGLE_ISSUERS
    ):
        caller = CallerContext(
            authentication=caller.authentication,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=configured_issuer), subject=subject.subject),
        )
    return resolve_usage_owner(caller)
