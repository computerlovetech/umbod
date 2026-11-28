import asyncio
import json

import jwt
from anyio import to_thread
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError, PyJWKSetError
from pydantic import ValidationError

from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError, JwtVerifier
from umbod.core.connectors.downstream_mcp.adapters.identity import simulated_user_claims
from umbod.core.connectors.downstream_mcp.personal.connections.development_identity_models import SimulatedUserIdentity


JWKS_REQUEST_TIMEOUT_SECONDS = 3.0


class ProductionJwksJwtVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str) -> None:
        if not issuer.strip() or not audience.strip():
            raise ValueError("Production admin JWT verification requires OIDC issuer and audience")
        self.jwks_client = PyJWKClient(jwks_url, timeout=JWKS_REQUEST_TIMEOUT_SECONDS)
        self.issuer = issuer
        self.audience = audience
        self._verification_slot = asyncio.Semaphore(1)

    async def verify_async(self, token: str) -> JwtClaims:
        await self._verification_slot.acquire()
        verification = asyncio.create_task(to_thread.run_sync(self.verify, token))
        verification.add_done_callback(self._release_verification_slot)
        return await asyncio.shield(verification)

    def _release_verification_slot(self, verification: asyncio.Task[JwtClaims]) -> None:
        self._verification_slot.release()
        if not verification.cancelled():
            verification.exception()

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
        return JwtClaims(claims=simulated_user_claims(SimulatedUserIdentity(
            user_id=self.user_id,
            email=self.email,
            name=self.name,
            membership_claim=self.membership_claim,
            required_membership=self.required_membership,
            simulated_admin=self.simulated_admin,
        )))


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


async def verify_request_jwt(verifier: JwtVerifier, token: str) -> JwtClaims:
    if type(verifier) is ProductionJwksJwtVerifier:
        return await verifier.verify_async(token)
    return verifier.verify(token)
