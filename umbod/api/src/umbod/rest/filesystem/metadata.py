from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.access import CallerNodeSummary
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.errors import WrongNodeKind
from umbod.core.filesystem.updates import FilesystemNodeUpdates, NodeChanges

from .deletion import expected_revision
from .deps import (
    get_filesystem_browsing, get_filesystem_caller, get_filesystem_deletion, get_filesystem_updates,
)
from .errors import filesystem_errors

router = APIRouter()
Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Updates = Annotated[FilesystemNodeUpdates, Depends(get_filesystem_updates)]
Browsing = Annotated[FilesystemBrowsing, Depends(get_filesystem_browsing)]
Deletion = Annotated[FilesystemDeletion, Depends(get_filesystem_deletion)]


@router.options("/nodes/{node_id}", status_code=204, response_class=Response)
async def check_node_eligibility(
    node_id: UUID, caller: Caller, browsing: Browsing, updates: Updates, deletion: Deletion,
) -> Response:
    allowed = ["GET", "OPTIONS"]
    with filesystem_errors():
        await browsing.get_node(caller, node_id)
        try:
            await updates.check_update_eligibility(caller, node_id)
        except PermissionDenied:
            pass
        else:
            allowed.append("PATCH")
        try:
            await deletion.check_delete_eligibility(caller, node_id)
        except (PermissionDenied, WrongNodeKind):
            pass
        else:
            allowed.append("DELETE")
    return Response(status_code=204, headers={"Allow": ", ".join(allowed), "Cache-Control": "no-store"})


@router.patch(
    "/nodes/{node_id}", response_model=CallerNodeSummary,
    summary="Update file or directory name, parent or metadata without changing content",
    description="Permissions and visibility reflect policy inside the update transaction; later changes require fresh inspection.",
    openapi_extra={"parameters": [{
        "name": "If-Match", "in": "header", "required": True,
        "description": "One strong quoted positive numeric revision of up to 19 digits.",
        "schema": {"type": "string", "pattern": r'^"[1-9][0-9]{0,18}"$'},
    }]},
    responses={
        403: {"description": "Missing, undiscoverable or unauthorized node."},
        412: {"description": "Node revision no longer matches If-Match."},
        428: {"description": "If-Match is required."},
    },
)
async def update_node(
    node_id: UUID, body: NodeChanges, caller: Caller,
    updates: Updates, response: Response,
    revision: Annotated[int, Depends(expected_revision)],
) -> CallerNodeSummary:
    with filesystem_errors():
        node = await updates.update_node(
            caller, node_id, body.to_core_patch(), expected_revision=revision,
        )
    response.headers["ETag"] = f'"{node.revision}"'
    response.headers["Cache-Control"] = "no-store"
    return node
