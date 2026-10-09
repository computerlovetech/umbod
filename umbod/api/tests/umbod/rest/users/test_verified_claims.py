import pytest
from fastapi import HTTPException, Request

from umbod.rest.authentication import JwtClaims, JwtVerificationError
from umbod.rest.authentication.deps import (
    VERIFIED_ACCESS_CLAIMS_STATE_KEY,
    get_verified_access_claims,
)
from umbod.rest.users.current_user import CurrentUserProvider, JwtCurrentUserProvider
from umbod.rest.users.mapping import AccessClaimsUserProfileProvider, ClaimProfileMapper


class RejectingVerifier:
    def verify(self, token: str) -> JwtClaims:
        raise JwtVerificationError("Access verification must not run again")


def test_current_user_reuses_middleware_verified_claims() -> None:
    request = Request({"type": "http", "headers": []})
    setattr(
        request.state,
        VERIFIED_ACCESS_CLAIMS_STATE_KEY,
        JwtClaims(claims={"sub": "verified", "name": "Access"}),
    )
    provider: CurrentUserProvider = JwtCurrentUserProvider(
        "X-Access",
        RejectingVerifier(),
        AccessClaimsUserProfileProvider(ClaimProfileMapper("name", "email", "picture")),
        "X-Profile",
    )
    response = provider.get_current_user(request)
    assert response.id == "verified"
    assert response.name == "Access"


@pytest.mark.parametrize("value", [None, {}, "unverified"])
def test_verified_claims_dependency_rejects_missing_or_untyped_state(
    value: object,
) -> None:
    request = Request({"type": "http", "headers": []})
    setattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, value)
    with pytest.raises(HTTPException) as error:
        get_verified_access_claims(request)
    assert error.value.status_code == 401
