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


class RestCallerContextProvider:
    def __init__(
        self, claims: JwtClaims, authentication: AuthenticationProvenance
    ) -> None:
        subject = claims.claims.get("sub")
        issuer = claims.claims.get("iss")
        self._context = CallerContext(
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

    def get_context(self) -> CallerContext:
        return self._context


def authentication_provenance(verifier: JwtVerifier) -> AuthenticationProvenance:
    if type(verifier) is ProductionJwksJwtVerifier:
        return AuthenticationProvenance.UPSTREAM_VERIFIED
    if type(verifier) is SimulatedJwtVerifier:
        return AuthenticationProvenance.LOCAL_SIMULATION
    if type(verifier) is SemanticJwtVerifier:
        return AuthenticationProvenance.LOCAL_SEMANTIC
    return AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
