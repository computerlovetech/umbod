from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from umbod.core.connectors.downstream_mcp.management import utc_clock
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipalProvider, PersonalConnectionKey, PersonalConnectorInventory, PersonalConnectorQuery, PersonalConnectorUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealth, PersonalAuthorizationHealthQuery
from umbod.core.connectors.downstream_mcp.personal_connections.health_ports import PersonalAuthorizationHealthStore
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_stores

from .dependencies import get_personal_connector_inventory, get_personal_principal_provider


router = APIRouter(prefix="/connectors/mcp", tags=["personal-mcp-connections"])


def get_personal_authorization_health(
    stores: Annotated[DownstreamMcpStores, Depends(get_downstream_stores)],
) -> PersonalAuthorizationHealthStore:
    return stores.personal_authorization_health


@router.get("/{connector_id}/authorization", response_model=PersonalAuthorizationHealth)
async def get_personal_authorization(
    connector_id: str,
    response: Response,
    inventory: Annotated[PersonalConnectorInventory, Depends(get_personal_connector_inventory)],
    principal: Annotated[CanonicalPrincipalProvider, Depends(get_personal_principal_provider)],
    health: Annotated[PersonalAuthorizationHealthStore, Depends(get_personal_authorization_health)],
) -> PersonalAuthorizationHealth:
    response.headers["Cache-Control"] = "no-store"
    owner = await principal.get_principal()
    if owner is None:
        raise HTTPException(status_code=403, detail={"code": "personal_identity_unavailable"}, headers={"Cache-Control": "no-store"})
    try:
        await inventory.get(PersonalConnectorQuery(connector_id=connector_id))
        return await health.get(PersonalAuthorizationHealthQuery(key=PersonalConnectionKey(principal=owner, connector_id=connector_id), now=utc_clock()))
    except PersonalConnectorUnavailable:
        raise HTTPException(status_code=404, detail={"code": "personal_connector_not_found"}, headers={"Cache-Control": "no-store"}) from None
    except Exception:
        pass
    raise HTTPException(status_code=503, detail={"code": "personal_authorization_health_unavailable"}, headers={"Cache-Control": "no-store"})
