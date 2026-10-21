from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from umbod.core.connectors.downstream_mcp.personal_connections import (
    PersonalConnectorInventory,
    PersonalConnectorQuery,
    PersonalConnectorUnavailable,
    SetPersonalConnectorEnablement,
)

from .dependencies import get_personal_connector_inventory
from .schemas import (
    PersonalConnectorListResponse,
    PersonalConnectorResponse,
    PersonalEnablementRequest,
    present_personal_connector,
)


router = APIRouter(prefix="/connectors/mcp", tags=["personal-mcp-connections"])
Inventory = Annotated[PersonalConnectorInventory, Depends(get_personal_connector_inventory)]


def unavailable_connector() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "personal_connector_not_found"})


@router.get("", response_model=PersonalConnectorListResponse)
async def list_personal_connectors(inventory: Inventory) -> PersonalConnectorListResponse:
    selections = await inventory.list()
    return PersonalConnectorListResponse(connectors=tuple(
        present_personal_connector(selection) for selection in selections.connectors
    ))


@router.get("/{connector_id}", response_model=PersonalConnectorResponse)
async def get_personal_connector(connector_id: str, inventory: Inventory) -> PersonalConnectorResponse:
    try:
        selection = await inventory.get(PersonalConnectorQuery(connector_id=connector_id))
    except PersonalConnectorUnavailable:
        raise unavailable_connector() from None
    return present_personal_connector(selection)


@router.put("/{connector_id}/enablement", response_model=PersonalConnectorResponse)
async def set_personal_connector_enablement(
    connector_id: str, body: PersonalEnablementRequest, inventory: Inventory,
) -> PersonalConnectorResponse:
    try:
        selection = await inventory.set_enabled(SetPersonalConnectorEnablement(
            connector_id=connector_id, enabled=body.enabled,
        ))
    except PersonalConnectorUnavailable:
        raise unavailable_connector() from None
    return present_personal_connector(selection)


@router.delete("/{connector_id}/authorization", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_personal_connector(connector_id: str, inventory: Inventory) -> Response:
    try:
        await inventory.disconnect(PersonalConnectorQuery(connector_id=connector_id))
    except PersonalConnectorUnavailable:
        raise unavailable_connector() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
