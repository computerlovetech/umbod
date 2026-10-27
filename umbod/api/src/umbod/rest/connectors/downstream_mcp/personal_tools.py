from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from umbod.core.capabilities.tools.names import PublicToolIdentitySource
from umbod.core.connectors.downstream_mcp.models import DiscoveredTool
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolPolicy, PersonalToolPolicyConflict, PersonalToolPolicyStore, PersonalToolPolicyUnavailable, ReplacePersonalToolPolicy
from umbod.core.connectors.downstream_mcp.personal_tools.models import UnconfiguredPersonalToolPolicy
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores, get_public_tool_identity_source
from umbod.rest.connectors.downstream_mcp.personal_validation import PersonalConfigurationValidationRoute
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories


class ReplacePersonalToolsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: str = Field(min_length=1, max_length=128)
    tools: tuple[DiscoveredTool, ...] = Field(max_length=256)


def get_personal_tool_policies(
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> PersonalToolPolicyStore:
    if not factories.settings.personal_connections.enabled:
        raise HTTPException(status_code=404, detail={"code": "personal_connections_unavailable"})
    return stores.personal_tool_policies


router = APIRouter(route_class=PersonalConfigurationValidationRoute)
PolicyStore = Annotated[PersonalToolPolicyStore, Depends(get_personal_tool_policies)]


@router.get("/{connector_id}/personal-tools", response_model=PersonalToolPolicy | UnconfiguredPersonalToolPolicy)
async def get_personal_tools(connector_id: str, store: PolicyStore) -> PersonalToolPolicy | UnconfiguredPersonalToolPolicy:
    try:
        return await store.get(ConnectorIdQuery(connector_id=connector_id))
    except PersonalToolPolicyUnavailable:
        raise HTTPException(status_code=404, detail={"code": "personal_tools_unavailable"}) from None


@router.put("/{connector_id}/personal-tools", response_model=PersonalToolPolicy)
async def replace_personal_tools(
    connector_id: str, request: ReplacePersonalToolsRequest, store: PolicyStore,
    identities: Annotated[PublicToolIdentitySource, Depends(get_public_tool_identity_source)],
) -> PersonalToolPolicy:
    try:
        replacement = await store.replace(ReplacePersonalToolPolicy(
            connector_id=connector_id, expected_revision=request.expected_revision,
            tools=request.tools, native_identities=await identities.identities(),
        ))
    except PersonalToolPolicyConflict:
        raise HTTPException(status_code=409, detail={"code": "personal_tools_conflict"}) from None
    except PersonalToolPolicyUnavailable:
        raise HTTPException(status_code=404, detail={"code": "personal_tools_unavailable"}) from None
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "invalid_personal_tool_configuration"}) from None
    return replacement.policy
