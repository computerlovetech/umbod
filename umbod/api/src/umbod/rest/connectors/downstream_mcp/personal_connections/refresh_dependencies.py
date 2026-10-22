from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.factory import configured_personal_oauth_refresh_provider
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipalProvider, PersonalConnectorInventory, VerifiedGroupMembership
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_ports import PersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_service import PersonalRefreshService
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores

from .dependencies import get_personal_connector_inventory, get_personal_group_membership, get_personal_principal_provider
from .oauth_dependencies import get_personal_callback_policy, oauth_clock, require_personal_oauth


async def get_personal_refresh_provider(
    enabled: Annotated[None, Depends(require_personal_oauth)],
    callback_policy: Annotated[CallbackURLPolicy, Depends(get_personal_callback_policy)],
) -> AsyncIterator[PersonalOAuthRefreshProvider]:
    async with configured_personal_oauth_refresh_provider(callback_policy) as provider:
        yield provider


async def get_personal_refresh_service(
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    groups: Annotated[VerifiedGroupMembership, Depends(get_personal_group_membership)],
    inventory: Annotated[PersonalConnectorInventory, Depends(get_personal_connector_inventory)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    provider: Annotated[PersonalOAuthRefreshProvider, Depends(get_personal_refresh_provider)],
) -> PersonalRefreshService:
    return PersonalRefreshService(principal, groups, inventory, stores.personal_refresh, provider, oauth_clock)
