from fastapi import HTTPException, Request

from umbod.rest.authentication.authorization import JwtClaims

VERIFIED_ACCESS_CLAIMS_STATE_KEY = "verified_access_claims"


def get_verified_access_claims(request: Request) -> JwtClaims:
    claims = getattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, None)
    if not isinstance(claims, JwtClaims):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return claims
