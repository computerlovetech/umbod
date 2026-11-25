from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.factory import configured_personal_oauth_setup_provider
from umbod.core.connectors.downstream_mcp.personal.oauth.diagnostics import PersonalOAuthFailureObserver
from umbod.core.connectors.downstream_mcp.personal.oauth.configuration import PersonalOAuthConfigurationUnavailable
from umbod.core.connectors.downstream_mcp.personal.oauth.setup import (
    PersonalOAuthSetupConflict,
    PersonalOAuthSetupProvider,
    PersonalOAuthSetupQuery,
    PersonalOAuthSetupService,
    PersonalOAuthSetupStatus,
    StartPersonalOAuthSetup,
)
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_setup import setup_clock
from .dependencies import Factories, get_downstream_stores
from .personal_connections.oauth_dependencies import get_personal_callback_policy, require_personal_oauth
from .personal_connections.oauth_diagnostics import get_setup_failure_observer


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: str = Field(min_length=1, max_length=128)


class SetupValidationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            if request.method == "POST":
                chunks: list[bytes] = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 2048:
                        return JSONResponse(status_code=413, content={"detail": {"code": "invalid_personal_oauth_setup"}})
                    chunks.append(chunk)
                request._body = b"".join(chunks)
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": {"code": "invalid_personal_oauth_setup"}})

        return bounded_handler


async def get_setup_provider(
    callback_policy: Annotated[CallbackURLPolicy, Depends(get_personal_callback_policy)],
    enabled: Annotated[None, Depends(require_personal_oauth)],
) -> AsyncIterator[PersonalOAuthSetupProvider]:
    async with configured_personal_oauth_setup_provider(callback_policy) as provider:
        yield provider


async def get_setup_service(
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    provider: Annotated[PersonalOAuthSetupProvider, Depends(get_setup_provider)],
    failures: Annotated[PersonalOAuthFailureObserver, Depends(get_setup_failure_observer)],
) -> PersonalOAuthSetupService:
    return PersonalOAuthSetupService(stores.personal_oauth_setup, provider, failures, setup_clock)


Service = Annotated[PersonalOAuthSetupService, Depends(get_setup_service)]
router = APIRouter(route_class=SetupValidationRoute)


def _callback(factories: Factories) -> str:
    return factories.settings.endpoints.api_base_url.rstrip("/") + "/api/oauth/downstream-mcp/callback"


def _setup_error(error: ValueError) -> HTTPException:
    if isinstance(error, PersonalOAuthSetupConflict):
        return HTTPException(status_code=409, detail={"code": "personal_oauth_setup_conflict"})
    return HTTPException(status_code=404, detail={"code": "personal_oauth_setup_unavailable"})


@router.get("/{connector_id}/personal-oauth/setup", response_model=PersonalOAuthSetupStatus)
async def get_setup(connector_id: str, service: Service, factories: Factories) -> PersonalOAuthSetupStatus:
    try:
        return await service.get(PersonalOAuthSetupQuery(connector_id=connector_id, redirect_uri=_callback(factories)))
    except PersonalOAuthConfigurationUnavailable as error:
        raise _setup_error(error) from None


async def _run(connector_id: str, request: SetupRequest, service: PersonalOAuthSetupService, factories: Factories, operation: str) -> PersonalOAuthSetupStatus:
    command = StartPersonalOAuthSetup(connector_id=connector_id, redirect_uri=_callback(factories), expected_revision=request.expected_revision, operation=operation)
    try:
        return await service.run(command)
    except (PersonalOAuthConfigurationUnavailable, PersonalOAuthSetupConflict) as error:
        raise _setup_error(error) from None


@router.post("/{connector_id}/personal-oauth/setup/discovery", response_model=PersonalOAuthSetupStatus)
async def discover_setup(connector_id: str, request: SetupRequest, service: Service, factories: Factories) -> PersonalOAuthSetupStatus:
    return await _run(connector_id, request, service, factories, "discovery")


@router.post("/{connector_id}/personal-oauth/setup/validation", response_model=PersonalOAuthSetupStatus)
async def validate_setup(connector_id: str, request: SetupRequest, service: Service, factories: Factories) -> PersonalOAuthSetupStatus:
    return await _run(connector_id, request, service, factories, "validation")
