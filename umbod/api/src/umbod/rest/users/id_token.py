import logging
from typing import Literal

from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
)

from umbod.rest.authentication.authorization import (
    JwtClaims,
    JwtVerificationError,
    JwtVerifier,
)
from umbod.rest.users.mapping import ClaimProfileMapper
from umbod.rest.users.profiles import UserProfile, UserProfileInput, UserProfileProvider

logger = logging.getLogger(__name__)
ProfileRejectionReason = Literal[
    "expired",
    "audience",
    "issuer",
    "signature",
    "invalid_token",
    "authorized_party",
    "subject_binding",
    "issuer_binding",
]


class ProfileTokenVerificationError(JwtVerificationError):
    def __init__(self, reason: ProfileRejectionReason) -> None:
        super().__init__(reason)
        self.reason = reason


class OidcProfileJwtVerifier:
    def __init__(self, verifier: JwtVerifier, client_id: str) -> None:
        self.verifier = verifier
        self.client_id = client_id

    def verify(self, token: str) -> JwtClaims:
        try:
            claims = self.verifier.verify(token)
        except JwtVerificationError as error:
            reason: ProfileRejectionReason = "invalid_token"
            for error_type, category in (
                (ExpiredSignatureError, "expired"),
                (InvalidAudienceError, "audience"),
                (InvalidIssuerError, "issuer"),
                (InvalidSignatureError, "signature"),
            ):
                if isinstance(error.__cause__, error_type):
                    reason = category
                    break
            raise ProfileTokenVerificationError(reason) from None
        audience = claims.claims.get("aud")
        authorized_party = claims.claims.get("azp")
        if ("azp" in claims.claims and authorized_party != self.client_id) or (
            isinstance(audience, list)
            and len(audience) > 1
            and authorized_party != self.client_id
        ):
            raise ProfileTokenVerificationError("authorized_party")
        return claims


class OidcIdTokenUserProfileProvider:
    def __init__(
        self,
        verifier: JwtVerifier,
        mapper: ClaimProfileMapper,
        fallback: UserProfileProvider,
    ) -> None:
        self.verifier = verifier
        self.mapper = mapper
        self.fallback = fallback

    def get_profile(self, profile_input: UserProfileInput) -> UserProfile:
        if not profile_input.header_present:
            return self.fallback.get_profile(profile_input)
        try:
            claims = self.verifier.verify(profile_input.token)
            subject = claims.claims.get("sub")
            issuer = claims.claims.get("iss")
            if not isinstance(
                subject, str
            ) or subject != profile_input.access_claims.claims.get("sub"):
                raise ProfileTokenVerificationError("subject_binding")
            if not isinstance(
                issuer, str
            ) or issuer != profile_input.access_claims.claims.get("iss"):
                raise ProfileTokenVerificationError("issuer_binding")
        except JwtVerificationError as error:
            reason = (
                error.reason
                if isinstance(error, ProfileTokenVerificationError)
                else "invalid_token"
            )
            logger.warning(
                "User profile enrichment rejected", extra={"reason_category": reason}
            )
            return self.fallback.get_profile(profile_input)
        return self.mapper.map(claims)
