from typing import Annotated

from fastapi import APIRouter, Depends, Request

from umbod.rest.authentication import JwtClaims
from umbod.rest.authentication.deps import get_verified_access_claims
from umbod.rest.user_catalogue.identity import catalogue_identity_key

from umbod.rest.users.current_user import CurrentUserProvider
from umbod.rest.users.deps import get_current_user_provider, get_user_capabilities
from umbod.rest.users.responses import UserCapabilitiesResponse, UserProfileResponse


def create_user_profile_router() -> APIRouter:
    router = APIRouter()

    @router.get("/profile", response_model=UserProfileResponse)
    def get_user_profile(
        request: Request,
        provider: Annotated[CurrentUserProvider, Depends(get_current_user_provider)],
        capabilities: Annotated[UserCapabilitiesResponse, Depends(get_user_capabilities)],
        claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
    ) -> UserProfileResponse:
        return UserProfileResponse(
            identity_key=catalogue_identity_key(claims.claims),
            user=provider.get_current_user(request), capabilities=capabilities,
        )

    return router
