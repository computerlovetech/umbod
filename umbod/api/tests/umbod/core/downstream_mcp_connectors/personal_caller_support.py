from umbod.core.callers import AuthenticationProvenance, CallerContext, GroupMembership, SubjectIdentity, UnavailableIssuer
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalCaller


def captured_personal_caller(principal: CanonicalPrincipal, group_ids: tuple[str, ...]) -> PersonalCaller:
    return PersonalCaller(
        caller=CallerContext(
            authentication=AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
            subject=SubjectIdentity(issuer=UnavailableIssuer(kind="unavailable"), subject=principal.subject),
        ),
        principal=principal,
        groups=GroupMembership(group_ids=group_ids),
    )
