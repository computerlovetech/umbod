import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.deletion import FilesystemDeletion

from .deps import get_filesystem_caller, get_filesystem_deletion
from .errors import filesystem_errors

router = APIRouter()
Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Deletion = Annotated[FilesystemDeletion, Depends(get_filesystem_deletion)]


def expected_revision(request: Request) -> int:
    if_match = request.headers.getlist("If-Match")
    if not if_match:
        raise HTTPException(428, detail={
            "code": "filesystem_precondition_required", "message": "If-Match is required.",
        })
    if len(if_match) != 1 or re.fullmatch(r'"[1-9][0-9]{0,18}"', if_match[0]) is None:
        raise HTTPException(422, detail=[{
            "loc": ["header", "If-Match"], "type": "value_error",
            "msg": "Expected one quoted positive numeric revision of up to 19 digits.",
        }])
    return int(if_match[0][1:-1])


@router.options("/nodes/{node_id}", status_code=204, response_class=Response)
async def check_delete_eligibility(node_id: UUID, caller: Caller, deletion: Deletion) -> Response:
    with filesystem_errors():
        await deletion.check_delete_eligibility(caller, node_id)
    return Response(status_code=204, headers={"Allow": "GET, DELETE, OPTIONS", "Cache-Control": "no-store"})


@router.delete(
    "/nodes/{node_id}", status_code=204, response_class=Response,
    summary="Permanently remove one file from the workspace",
    description="Removes the file namespace entry and its policies, not stored bytes. Directories and root cannot be removed.",
    openapi_extra={"parameters": [{
        "name": "If-Match", "in": "header", "required": True,
        "description": "One strong quoted positive numeric revision of up to 19 digits. Weak tags, wildcards and lists are unsupported.",
        "schema": {"type": "string", "pattern": r'^"[1-9][0-9]{0,18}"$'},
    }]},
    responses={
        403: {"description": "Missing, undiscoverable or unauthorized node."},
        409: {"description": "Authorized node is not a file."},
        412: {"description": "Node revision no longer matches If-Match."},
        428: {"description": "If-Match is required."},
    },
)
async def delete_file(
    node_id: UUID, caller: Caller, deletion: Deletion,
    revision: Annotated[int, Depends(expected_revision)],
) -> Response:
    with filesystem_errors():
        await deletion.delete_file(caller, node_id, expected_revision=revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
