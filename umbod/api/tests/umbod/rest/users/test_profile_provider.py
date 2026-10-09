import pytest

from umbod.rest.authentication import JwtClaims, JwtVerifier
from umbod.rest.users import (
    InMemoryUserProfileProvider,
    UserProfile,
    UserProfileInput,
    UserProfileProvider,
)
from umbod.rest.users.id_token import OidcIdTokenUserProfileProvider
from umbod.rest.users.mapping import ClaimProfileMapper


class InMemoryClaimsVerifier:
    def __init__(self, claims: JwtClaims) -> None:
        self.claims = claims

    def verify(self, token: str) -> JwtClaims:
        return self.claims


def test_in_memory_profile_port_returns_validated_profile() -> None:
    profile = UserProfile(name="Display", email="", picture="")
    provider: UserProfileProvider = InMemoryUserProfileProvider(profile)
    assert (
        provider.get_profile(
            UserProfileInput(
                access_claims=JwtClaims(claims={"sub": "user"}),
                token="",
                header_present=False,
            )
        )
        == profile
    )


@pytest.mark.parametrize("issuer", ["different", None, 123])
def test_profile_port_binds_issuer_to_access(
    issuer: object, caplog: pytest.LogCaptureFixture
) -> None:
    fallback = UserProfile(name="Fallback", email="", picture="")
    verifier: JwtVerifier = InMemoryClaimsVerifier(
        JwtClaims(claims={"iss": issuer, "sub": "user", "name": "Untrusted"})
    )
    provider: UserProfileProvider = OidcIdTokenUserProfileProvider(
        verifier,
        ClaimProfileMapper("name", "email", "picture"),
        InMemoryUserProfileProvider(fallback),
    )
    result = provider.get_profile(
        UserProfileInput(
            access_claims=JwtClaims(claims={"iss": "trusted", "sub": "user"}),
            token="secret",
            header_present=True,
        )
    )
    assert result == fallback
    assert caplog.records[-1].reason_category == "issuer_binding"
    assert "secret" not in caplog.text
