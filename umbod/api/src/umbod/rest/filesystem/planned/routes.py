from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from ..deps import require_filesystem_identity
from .deps import not_implemented
from .models import PatchNodeRequest, PlannedErrorResponse

PLANNED_RESPONSES = {
    501: {
        "model": PlannedErrorResponse,
        "description": "Planned operation; no item lookup, content access or mutation.",
        "headers": {"Cache-Control": {"schema": {"type": "string", "const": "no-store"}}},
    },
}
PLANNED_OPERATION = {"x-umbod-status": "planned"}
router = APIRouter(
    dependencies=[Depends(require_filesystem_identity)],
    responses=PLANNED_RESPONSES,
)
Revision = Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')]


@router.get("/nodes", status_code=501, response_model=PlannedErrorResponse,
            summary="Planned: list owned or shared nodes", openapi_extra=PLANNED_OPERATION)
async def list_nodes(scope: Literal["owned", "shared"]) -> NoReturn:
    not_implemented()


@router.put("/nodes/{node_id}/content", status_code=501, response_model=PlannedErrorResponse,
            summary="Planned: replace content", openapi_extra={
                **PLANNED_OPERATION,
                "requestBody": {"required": True, "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                }},
            })
async def put_content(node_id: UUID, if_match: Revision) -> NoReturn:
    not_implemented()


@router.patch("/nodes/{node_id}", status_code=501, response_model=PlannedErrorResponse,
              summary="Planned: rename or move node", openapi_extra=PLANNED_OPERATION)
async def patch_node(node_id: UUID, body: PatchNodeRequest, if_match: Revision) -> NoReturn:
    not_implemented()
