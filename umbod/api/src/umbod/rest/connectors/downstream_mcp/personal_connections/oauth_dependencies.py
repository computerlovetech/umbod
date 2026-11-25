from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.connectors.downstream_mcp.personal.connections.development_identity import local_personal_identity_enabled
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.factory import configured_personal_oauth_provider
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization import (
    PersonalOAuthCallbackService,
    PersonalOAuthProvider,
    PersonalOAuthService,
)
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores

from .dependencies import (
    Factories,
    get_personal_connector_inventory,
    get_personal_caller,
)
from umbod.core.connectors.downstream_mcp.personal.connections import PersonalCaller, PersonalConnectorInventory
from .oauth_policy import OAuthPolicy
from .oauth_diagnostics import get_oauth_failure_observer
from umbod.core.connectors.downstream_mcp.personal.oauth.diagnostics import PersonalOAuthFailureObserver


def require_personal_oauth(policy: OAuthPolicy) -> None:
    if not policy.enabled:
        raise HTTPException(status_code=404, detail={"code": "personal_oauth_unavailable"})


def get_personal_callback_policy(factories: Factories) -> CallbackURLPolicy:
    return CallbackURLPolicy.LOCAL_DEVELOPMENT if local_personal_identity_enabled(personal_identity_policy_from_app_config(factories.settings)) else CallbackURLPolicy.STRICT


async def get_personal_oauth_provider(
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    callback_policy: Annotated[CallbackURLPolicy, Depends(get_personal_callback_policy)],
    enabled: Annotated[None, Depends(require_personal_oauth)],
) -> AsyncIterator[PersonalOAuthProvider]:
    async with configured_personal_oauth_provider(callback_policy, stores.personal_oauth_applications) as provider:
        yield provider


def oauth_clock() -> datetime:
    return datetime.now(UTC)


async def get_personal_oauth_service(
    caller: Annotated[PersonalCaller, Depends(get_personal_caller)],
    inventory: Annotated[PersonalConnectorInventory, Depends(get_personal_connector_inventory)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    provider: Annotated[PersonalOAuthProvider, Depends(get_personal_oauth_provider)],
    factories: Factories,
    failures: Annotated[PersonalOAuthFailureObserver, Depends(get_oauth_failure_observer)],
) -> PersonalOAuthService:
    return PersonalOAuthService(
        caller, inventory, stores.definitions, stores.personal_connections,
        stores.personal_oauth_attempts, provider,
        factories.settings.endpoints.api_base_url.rstrip("/") + "/api/oauth/downstream-mcp/callback",
        oauth_clock, stores.personal_oauth_configurations, failures=failures,
    )


async def get_personal_oauth_callback_service(
    enabled: Annotated[None, Depends(require_personal_oauth)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    provider: Annotated[PersonalOAuthProvider, Depends(get_personal_oauth_provider)],
    failures: Annotated[PersonalOAuthFailureObserver, Depends(get_oauth_failure_observer)],
) -> PersonalOAuthCallbackService:
    return PersonalOAuthCallbackService(stores.personal_oauth_attempts, provider, oauth_clock, failures=failures)
