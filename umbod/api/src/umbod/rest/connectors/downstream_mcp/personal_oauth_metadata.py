from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.metadata import DiscoveredPersonalOAuthMetadataProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import SafeOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization import (
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.metadata import DiscoverPersonalOAuthMetadata, PersonalOAuthMetadataProvider, PersonalOAuthMetadataResult
from umbod.core.network import public_http_connection_pool
from .dependencies import Factories
from .preview_validation import BoundedPreviewRoute


class MetadataValidationRoute(BoundedPreviewRoute):
    @staticmethod
    def invalid_input_detail() -> dict[str, str]:
        return {"code": "personal_oauth_discovery_failed", "stage": "discovery", "reason": "invalid_response"}


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
