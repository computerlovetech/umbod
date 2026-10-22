from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.personal_connections.development_identity import local_personal_identity_enabled
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.factory import configured_personal_oauth_provider
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService, PersonalOAuthService
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores

from .dependencies import (
    Factories,
    get_personal_connector_inventory,
    get_personal_group_membership,
    get_personal_principal_provider,
)
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipalProvider, PersonalConnectorInventory, VerifiedGroupMembership


def require_personal_oauth(factories: Factories) -> None:
    if not factories.settings.personal_connections.oauth_enabled:
        raise HTTPException(status_code=404, detail={"code": "personal_oauth_unavailable"})


def get_personal_callback_policy(factories: Factories) -> CallbackURLPolicy:
    return CallbackURLPolicy.LOCAL_DEVELOPMENT if local_personal_identity_enabled(factories.settings) else CallbackURLPolicy.STRICT


async def get_personal_oauth_provider(
    callback_policy: Annotated[CallbackURLPolicy, Depends(get_personal_callback_policy)],
    enabled: Annotated[None, Depends(require_personal_oauth)],
) -> AsyncIterator[PersonalOAuthProvider]:
    async with configured_personal_oauth_provider(callback_policy) as provider:
        yield provider


def oauth_clock() -> datetime:
    return datetime.now(UTC)


async def get_personal_oauth_service(
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    groups: Annotated[VerifiedGroupMembership, Depends(get_personal_group_membership)],
    inventory: Annotated[PersonalConnectorInventory, Depends(get_personal_connector_inventory)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    provider: Annotated[PersonalOAuthProvider, Depends(get_personal_oauth_provider)],
    factories: Factories,
) -> PersonalOAuthService:
    return PersonalOAuthService(
        principal, groups, inventory, stores.definitions, stores.personal_connections,
        stores.personal_oauth_attempts, provider,
        factories.settings.endpoints.api_base_url.rstrip("/") + "/api/oauth/downstream-mcp/callback",
        oauth_clock, stores.personal_oauth_configurations,
    )


async def get_personal_oauth_callback_service(
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    provider: Annotated[PersonalOAuthProvider, Depends(get_personal_oauth_provider)],
) -> PersonalOAuthCallbackService:
    return PersonalOAuthCallbackService(stores.personal_oauth_attempts, provider, oauth_clock)
