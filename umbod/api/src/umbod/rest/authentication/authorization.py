from typing import Protocol

from umbod.rest.proxies import Model


class JwtClaims(Model):
    claims: dict[str, object]


class JwtVerificationError(Exception):
    pass


class JwtVerifier(Protocol):
    def verify(self, token: str) -> JwtClaims: ...


class AdminAuthorizationPolicy(Model):
    membership_claim: str
    required_membership: str


class AdminAuthorizationService:
    def __init__(self, jwt_verifier: JwtVerifier, policy: AdminAuthorizationPolicy) -> None:
        self.jwt_verifier = jwt_verifier
        self.policy = policy

    def verify_claims(self, token: str) -> JwtClaims:
        return self.jwt_verifier.verify(token)

    def is_authorized(self, claims: JwtClaims) -> bool:
        membership_value = claims.claims.get(self.policy.membership_claim)
        if not isinstance(membership_value, list):
            return False
        return any(
            value == self.policy.required_membership
            for value in membership_value
            if isinstance(value, str)
        )
