from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.connectors.downstream_mcp.personal_connections import (
    CanonicalPrincipalProvider,
    PersonalConnectionService,
    PersonalConnectorInventory,
    PersonalConnectorInventoryService,
    PersonalIdentityPrincipalProvider,
)
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.core.permissions import GroupPermissionStore
from umbod.core.callers import GroupMembership
from umbod.core.connectors.downstream_mcp.adapters.identity import personal_identity_facts, personal_group_membership
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
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
    provider = PersonalIdentityPrincipalProvider(personal_identity_policy_from_app_config(factories.settings), personal_identity_facts(claims.claims))
    if await provider.get_principal() is None:
        raise HTTPException(status_code=403, detail={"code": "personal_identity_unavailable"})
    return provider


def get_personal_group_membership(factories: Factories, claims: Claims) -> GroupMembership:
    return personal_group_membership(claims.claims.get(factories.settings.mcp.permission_group_claim))


async def get_personal_connector_inventory(
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    groups: Annotated[GroupMembership, Depends(get_personal_group_membership)],
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
