from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .oauth_callback import callback_response, router
from .oauth_policy import PersonalOAuthPolicy, get_personal_oauth_policy


def create_personal_oauth_callback_app(
    dependency_factories: ConnectorApiDependencyFactories,
    policy: PersonalOAuthPolicy,
) -> FastAPI:
    settings = dependency_factories.settings
    callback_app = FastAPI(
        title="umbod-personal-oauth-callback", docs_url=None, redoc_url=None,
        openapi_url=None, redirect_slashes=False,
    )
    callback_app.include_router(router)

    def provide_dependency_factories() -> ConnectorApiDependencyFactories:
        return dependency_factories

    def provide_personal_oauth_policy() -> PersonalOAuthPolicy:
        return policy

    callback_app.dependency_overrides[get_connector_api_dependency_factories] = provide_dependency_factories
    callback_app.dependency_overrides[get_personal_oauth_policy] = provide_personal_oauth_policy

    @callback_app.middleware("http")
    async def protect_callback_response(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            return callback_response(400, settings.endpoints.site_base_url.rstrip("/") + "/dashboard")
        if response.status_code != 200:
            return callback_response(400, settings.endpoints.site_base_url.rstrip("/") + "/dashboard")
        return response

    return callback_app
