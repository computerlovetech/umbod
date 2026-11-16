from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.metadata import DiscoveredPersonalOAuthMetadataProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import SafeOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from umbod.core.connectors.downstream_mcp.personal_oauth_metadata import DiscoverPersonalOAuthMetadata, PersonalOAuthMetadataProvider, PersonalOAuthMetadataResult
from umbod.core.network import public_http_connection_pool
from .dependencies import Factories


class MetadataValidationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            try:
                chunks: list[bytes] = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 12288:
                        return JSONResponse(status_code=413, content={"detail": {"code": "personal_oauth_discovery_failed", "stage": "discovery", "reason": "invalid_response"}}, headers={"Cache-Control": "no-store"})
                    chunks.append(chunk)
                request._body = b"".join(chunks)
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse(status_code=422, content={"detail": {"code": "personal_oauth_discovery_failed", "stage": "discovery", "reason": "invalid_response"}})
            except HTTPException as error:
                error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
                raise
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded_handler


def require_metadata_registration(factories: Factories) -> None:
    if not factories.settings.personal_connections.enabled:
        raise HTTPException(status_code=404, detail={"code": "personal_connections_unavailable"})


async def get_metadata_provider() -> AsyncIterator[PersonalOAuthMetadataProvider]:
    async with public_http_connection_pool(max_connections=10) as pool:
        yield DiscoveredPersonalOAuthMetadataProvider(SafeOAuthHttpTransport(pool=pool))


router = APIRouter(route_class=MetadataValidationRoute, dependencies=[Depends(require_metadata_registration)])


@router.post("/personal-oauth/discovery", response_model=PersonalOAuthMetadataResult)
async def discover_metadata(
    command: DiscoverPersonalOAuthMetadata,
    provider: Annotated[PersonalOAuthMetadataProvider, Depends(get_metadata_provider)],
) -> PersonalOAuthMetadataResult:
    try:
        return await provider.discover(command)
    except (PersonalOAuthProviderUnsupported, PersonalOAuthProviderFailure) as error:
        raise HTTPException(
            status_code=422 if isinstance(error, PersonalOAuthProviderUnsupported) else 502,
            detail={"code": "personal_oauth_discovery_failed", "stage": error.evidence.stage, "reason": error.evidence.reason},
            headers={"Cache-Control": "no-store"},
        ) from None
