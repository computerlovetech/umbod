from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.core.connectors.downstream_mcp.personal_connections import (
    PersonalCaller,
    PersonalConnectionService,
    PersonalConnectorInventory,
    PersonalConnectorInventoryService,
    ResolvedPersonalIdentity,
)
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.core.permissions import GroupPermissionStore
from umbod.core.connectors.downstream_mcp.adapters.identity import personal_identity_facts, personal_group_membership
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.mcp_permissions.dependencies import get_group_permission_store


Factories = Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)]
Claims = Annotated[JwtClaims, Depends(get_verified_access_claims)]


async def get_personal_caller(
    factories: Factories, claims: Claims,
    caller: Annotated[CallerContext, Depends(get_caller_context)],
) -> PersonalCaller:
    resolution = canonical_principal(personal_identity_policy_from_app_config(factories.settings), personal_identity_facts(claims.claims))
    if caller.authentication == AuthenticationProvenance.UNAVAILABLE or not isinstance(resolution, ResolvedPersonalIdentity):
        raise HTTPException(status_code=403, detail={"code": "personal_identity_unavailable"})
    return PersonalCaller(
        caller=caller, principal=resolution.principal,
        groups=personal_group_membership(claims.claims.get(factories.settings.mcp.permission_group_claim)),
    )


async def get_personal_connector_inventory(
    caller: Annotated[PersonalCaller, Depends(get_personal_caller)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    permissions: Annotated[GroupPermissionStore, Depends(get_group_permission_store)],
    factories: Factories,
) -> PersonalConnectorInventory:
    descriptions = await factories.connector_capability_description_override_store.create()
    return PersonalConnectorInventoryService(
        definitions=stores.definitions,
        publishing=stores.publishing,
        permissions=permissions,
        groups=caller.groups,
        connections=PersonalConnectionService(caller, stores.personal_connections),
        descriptions=descriptions,
    )
