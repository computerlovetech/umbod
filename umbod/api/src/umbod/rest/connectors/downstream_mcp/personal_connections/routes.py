from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from umbod.core.connectors.downstream_mcp.personal_connections import (
    PersonalConnectorInventory,
    PersonalConnectorQuery,
    PersonalConnectorUnavailable,
    SetPersonalConnectorEnablement,
)

from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolRuntime
from .runtime import get_personal_tool_runtime
from .dependencies import get_personal_connector_inventory
from .schemas import (
    PersonalConnectorListResponse,
    PersonalConnectorResponse,
    PersonalEnablementRequest,
    present_personal_connector,
)


router = APIRouter(prefix="/connectors/mcp", tags=["personal-mcp-connections"])
Inventory = Annotated[PersonalConnectorInventory, Depends(get_personal_connector_inventory)]
Runtime = Annotated[PersonalToolRuntime, Depends(get_personal_tool_runtime)]


def unavailable_connector() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "personal_connector_not_found"})


@router.get("", response_model=PersonalConnectorListResponse)
async def list_personal_connectors(inventory: Inventory, runtime: Runtime) -> PersonalConnectorListResponse:
    selections = await inventory.list()
    available = frozenset(record.definition.connector_id for record in await runtime.list_tools())
    return PersonalConnectorListResponse(connectors=tuple(
        present_personal_connector(selection, available) for selection in selections.connectors
    ))


@router.get("/{connector_id}", response_model=PersonalConnectorResponse)
async def get_personal_connector(connector_id: str, inventory: Inventory, runtime: Runtime) -> PersonalConnectorResponse:
    try:
        selection = await inventory.get(PersonalConnectorQuery(connector_id=connector_id))
    except PersonalConnectorUnavailable:
        raise unavailable_connector() from None
    return present_personal_connector(selection, frozenset(record.definition.connector_id for record in await runtime.list_tools()))


@router.put("/{connector_id}/enablement", response_model=PersonalConnectorResponse)
async def set_personal_connector_enablement(
    connector_id: str, body: PersonalEnablementRequest, inventory: Inventory, runtime: Runtime,
) -> PersonalConnectorResponse:
    try:
        selection = await inventory.set_enabled(SetPersonalConnectorEnablement(
            connector_id=connector_id, enabled=body.enabled,
        ))
    except PersonalConnectorUnavailable:
        raise unavailable_connector() from None
    return present_personal_connector(selection, frozenset(record.definition.connector_id for record in await runtime.list_tools()))


@router.delete("/{connector_id}/authorization", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_personal_connector(connector_id: str, inventory: Inventory) -> Response:
    try:
        await inventory.disconnect(PersonalConnectorQuery(connector_id=connector_id))
    except PersonalConnectorUnavailable:
        raise unavailable_connector() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
