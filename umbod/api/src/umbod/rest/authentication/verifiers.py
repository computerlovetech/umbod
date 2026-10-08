import json
import jwt

from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError, PyJWKSetError
from pydantic import ValidationError

from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError


class ProductionJwksJwtVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str) -> None:
        if not issuer.strip() or not audience.strip():
            raise ValueError("Production admin JWT verification requires OIDC issuer and audience")
        self.jwks_client = PyJWKClient(jwks_url)
        self.issuer = issuer
        self.audience = audience

    def verify(self, token: str) -> JwtClaims:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "exp", "sub"]},
            )
        except (InvalidTokenError, PyJWKClientError, PyJWKSetError) as error:
            raise JwtVerificationError("Invalid JWT") from error
        return JwtClaims(claims=dict(claims))


class SimulatedJwtVerifier:
    def __init__(
        self,
        user_id: str,
        email: str,
        name: str,
        membership_claim: str,
        required_membership: str,
        simulated_admin: bool,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.name = name
        self.membership_claim = membership_claim
        self.required_membership = required_membership
        self.simulated_admin = simulated_admin

    def verify(self, token: str) -> JwtClaims:
        claims: dict[str, object] = {
            "sub": self.user_id,
            "email": self.email,
            "name": self.name,
        }
        if self.simulated_admin:
            claims[self.membership_claim] = [self.required_membership]
        return JwtClaims(claims=claims)


class SemanticJwtVerifier:
    def verify(self, token: str) -> JwtClaims:
        try:
            token_data = json.loads(token)
        except json.JSONDecodeError as error:
            raise JwtVerificationError("Invalid JWT") from error
        if not isinstance(token_data, dict):
            raise JwtVerificationError("Invalid JWT")
        if token_data.get("signature") != "trusted":
            raise JwtVerificationError("Untrusted JWT")
        try:
            return JwtClaims(claims=token_data.get("claims", {}))
        except ValidationError as error:
            raise JwtVerificationError("Invalid JWT claims") from error
