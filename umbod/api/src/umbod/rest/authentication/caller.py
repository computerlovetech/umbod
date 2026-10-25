from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.rest.authentication.authorization import JwtClaims, JwtVerifier
from umbod.rest.authentication.verifiers import (
    ProductionJwksJwtVerifier,
    SemanticJwtVerifier,
    SimulatedJwtVerifier,
)


def caller_context_from_claims(
    claims: JwtClaims, authentication: AuthenticationProvenance,
) -> CallerContext:
    subject = claims.claims.get("sub")
    issuer = claims.claims.get("iss")
    return CallerContext(
        authentication=authentication,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value=issuer)
            if isinstance(issuer, str)
            else UnavailableIssuer(kind="unavailable"),
            subject=subject,
        )
        if isinstance(subject, str)
        else UnavailableSubject(kind="unavailable"),
    )


def authentication_provenance(verifier: JwtVerifier) -> AuthenticationProvenance:
    if type(verifier) is ProductionJwksJwtVerifier:
        return AuthenticationProvenance.UPSTREAM_VERIFIED
    if type(verifier) is SimulatedJwtVerifier:
        return AuthenticationProvenance.LOCAL_SIMULATION
    if type(verifier) is SemanticJwtVerifier:
        return AuthenticationProvenance.LOCAL_SEMANTIC
    return AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
