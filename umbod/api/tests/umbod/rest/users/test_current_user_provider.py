from fastapi import HTTPException, Request
import pytest

from umbod.rest.authentication import JwtClaims, JwtVerificationError
from umbod.rest.users.current_user import CurrentUserProvider, JwtCurrentUserProvider


class FakeJwtVerifier:
    def __init__(self, claims: dict[str, object], raises_error: bool) -> None:
        self.claims = claims
        self.raises_error = raises_error
        self.verified_token: str | None = None

    def verify(self, token: str) -> JwtClaims:
        self.verified_token = token
        if self.raises_error:
            raise JwtVerificationError()
        return JwtClaims(claims=self.claims)


def _create_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = []
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode(), value.encode()))
    return Request({"type": "http", "method": "GET", "path": "/users", "headers": raw_headers})


def test_jwt_provider_returns_claim_user() -> None:
    verifier = FakeJwtVerifier(
        {
            "sub": "user-123",
            "email": "alex@example.com",
            "name": "Alex",
            "picture": "https://example.com/a.png",
        },
        False,
    )
    provider = JwtCurrentUserProvider("X-Forwarded-Access-Token", verifier)

    current_user = provider.get_current_user(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert current_user.id == "user-123"
    assert current_user.email == "alex@example.com"
    assert current_user.name == "Alex"
    assert current_user.picture == "https://example.com/a.png"
    assert verifier.verified_token == "token"


def test_jwt_provider_verifies_empty_token_when_header_is_missing() -> None:
    verifier = FakeJwtVerifier({"sub": "user-123", "email": "alex@example.com"}, False)
    provider = JwtCurrentUserProvider("X-Forwarded-Access-Token", verifier)

    current_user = provider.get_current_user(_create_request())

    assert current_user.id == "user-123"
    assert verifier.verified_token == ""


def test_jwt_provider_rejects_invalid_token() -> None:
    provider = JwtCurrentUserProvider("X-Forwarded-Access-Token", FakeJwtVerifier({}, True))

    with pytest.raises(HTTPException) as error:
        provider.get_current_user(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"email": "alex@example.com"}, id="missing_subject"),
        pytest.param({"sub": "user-123"}, id="missing_email"),
    ],
)
def test_jwt_provider_requires_subject_and_email(claims: dict[str, object]) -> None:
    provider = JwtCurrentUserProvider("X-Forwarded-Access-Token", FakeJwtVerifier(claims, False))

    with pytest.raises(HTTPException) as error:
        provider.get_current_user(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert error.value.status_code == 401


def test_jwt_provider_defaults_non_string_optional_claims() -> None:
    provider = JwtCurrentUserProvider(
        "X-Forwarded-Access-Token",
        FakeJwtVerifier(
            {"sub": "user-123", "email": "alex@example.com", "name": 123, "picture": 456}, False
        ),
    )

    current_user = provider.get_current_user(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert current_user.name == "unknown"
    assert current_user.picture is None


def test_jwt_provider_is_protocol_compatible() -> None:
    provider: CurrentUserProvider = JwtCurrentUserProvider(
        "X-Forwarded-Access-Token",
        FakeJwtVerifier({"sub": "user-123", "email": "alex@example.com"}, False),
    )

    current_user = provider.get_current_user(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert current_user.id == "user-123"
