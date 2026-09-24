from fastapi import APIRouter, Request

from umbod.rest.authentication.middleware import APISettingsPort, JwtVerifierFactory
from umbod.rest.users.current_user import JwtCurrentUserProvider
from umbod.rest.users.responses import CurrentUserResponse


def create_current_user_router(settings: APISettingsPort) -> APIRouter:
    router = APIRouter()
    authentication_settings = settings.admin_authentication
    current_user_provider = JwtCurrentUserProvider(
        authentication_settings.jwt_header_name,
        JwtVerifierFactory().create(settings),
    )

    @router.get("/users", response_model=CurrentUserResponse)
    async def get_current_user(request: Request) -> CurrentUserResponse:
        return current_user_provider.get_current_user(request)

    return router
