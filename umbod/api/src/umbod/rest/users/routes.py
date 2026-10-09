from typing import Annotated

from fastapi import APIRouter, Depends, Request

from umbod.rest.users.current_user import CurrentUserProvider
from umbod.rest.users.deps import get_current_user_provider
from umbod.rest.users.responses import CurrentUserResponse


def create_current_user_router() -> APIRouter:
    router = APIRouter()

    @router.get("/users", response_model=CurrentUserResponse)
    def get_current_user(
        request: Request,
        provider: Annotated[CurrentUserProvider, Depends(get_current_user_provider)],
    ) -> CurrentUserResponse:
        return provider.get_current_user(request)

    return router
