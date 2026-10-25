from fastapi import HTTPException, Request

from umbod.core.callers import CallerContext
from umbod.rest.authentication.authorization import JwtClaims

VERIFIED_ACCESS_CLAIMS_STATE_KEY = "verified_access_claims"
CALLER_CONTEXT_STATE_KEY = "caller_context"


def get_caller_context(request: Request) -> CallerContext:
    context = getattr(request.state, CALLER_CONTEXT_STATE_KEY, None)
    if not isinstance(context, CallerContext):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return context


def get_verified_access_claims(request: Request) -> JwtClaims:
    claims = getattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, None)
    if not isinstance(claims, JwtClaims):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return claims
