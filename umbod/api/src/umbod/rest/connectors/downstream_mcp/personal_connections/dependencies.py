from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.connectors.downstream_mcp.personal_connections import (
    CanonicalPrincipalProvider,
    PersonalConnectionService,
    PersonalConnectorInventory,
    PersonalConnectorInventoryService,
    VerifiedClaimsPrincipalProvider,
    VerifiedGroupMembership,
)
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.core.permissions import GroupPermissionStore
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_verified_access_claims
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.dependencies import get_group_permission_store


Factories = Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]
Claims = Annotated[JwtClaims, Depends(get_verified_access_claims)]


async def get_personal_principal_provider(
    factories: Factories, claims: Claims,
) -> CanonicalPrincipalProvider:
    provider = VerifiedClaimsPrincipalProvider(factories.settings, claims.claims)
    if await provider.get_principal() is None:
        raise HTTPException(status_code=403, detail={"code": "personal_identity_unavailable"})
    return provider


def get_personal_group_membership(factories: Factories, claims: Claims) -> VerifiedGroupMembership:
    value = claims.claims.get(factories.settings.mcp.permission_group_claim)
    if isinstance(value, str):
        groups = (value,) if value.strip() else ()
    elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        groups = tuple(item for item in value if item.strip())
    else:
        groups = ()
    return VerifiedGroupMembership(group_ids=tuple(sorted(set(groups))))


async def get_personal_connector_inventory(
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    groups: Annotated[VerifiedGroupMembership, Depends(get_personal_group_membership)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    permissions: Annotated[GroupPermissionStore, Depends(get_group_permission_store)],
    factories: Factories,
) -> PersonalConnectorInventory:
    descriptions = await factories.connector_capability_description_override_store.create()
    return PersonalConnectorInventoryService(
        definitions=stores.definitions,
        publishing=stores.publishing,
        permissions=permissions,
        groups=groups,
        connections=PersonalConnectionService(principal, stores.personal_connections),
        descriptions=descriptions,
    )
