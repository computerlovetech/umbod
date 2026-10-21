from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.factory import create_personal_mcp_transport
from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipalProvider, PersonalConnectionKey, VerifiedGroupMembership
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryService, PersonalToolPolicyUnavailable
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories

from .dependencies import get_personal_group_membership, get_personal_principal_provider


class DiscoverPersonalToolsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def get_personal_tool_transport(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
) -> PersonalMcpTransport:
    if not factories.settings.personal_connections.oauth_enabled:
        raise HTTPException(status_code=404, detail={"code": "personal_oauth_unavailable"})
    return create_personal_mcp_transport()


def get_personal_tool_discovery(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
    transport: Annotated[PersonalMcpTransport, Depends(get_personal_tool_transport)],
) -> PersonalToolDiscoveryService:
    if not factories.settings.personal_connections.oauth_enabled:
        raise HTTPException(status_code=404, detail={"code": "personal_oauth_unavailable"})
    return PersonalToolDiscoveryService(stores.personal_tool_policies, stores.personal_runtime_authorizations, stores.personal_tool_access, transport, utc_clock)


router = APIRouter(prefix="/connectors/mcp", tags=["personal-mcp-connections"])


async def validate_discovery_body(request: Request) -> None:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(status_code=422, detail={"code": "invalid_personal_tools_request"})
    try:
        DiscoverPersonalToolsRequest.model_validate_json(bytes(body))
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "invalid_personal_tools_request"}) from None


@router.post("/{connector_id}/tools/discovery", status_code=204)
async def discover_personal_tools(
    connector_id: str, request: Request,
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    groups: Annotated[VerifiedGroupMembership, Depends(get_personal_group_membership)],
    discovery: Annotated[PersonalToolDiscoveryService, Depends(get_personal_tool_discovery)],
) -> Response:
    await validate_discovery_body(request)
    owner = await principal.get_principal()
    if owner is None:
        raise HTTPException(status_code=403, detail={"code": "personal_identity_unavailable"})
    try:
        await discovery.discover(PersonalRuntimeAuthorizationQuery(key=PersonalConnectionKey(principal=owner, connector_id=connector_id), group_ids=groups.group_ids, now=utc_clock()))
    except (PersonalRuntimeUnavailable, PersonalToolPolicyUnavailable):
        raise HTTPException(status_code=409, detail={"code": "personal_tool_discovery_unavailable"}) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
