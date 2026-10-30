import re
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, model_validator

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.group_policy import GroupPolicy
from umbod.core.filesystem.sharing import (
    EligibleSharingGroups, FilesystemSharing, NodeGroupPolicyView, ReplaceNodeGroupPolicy,
)

from .deps import get_filesystem_caller, get_filesystem_sharing
from .errors import filesystem_errors

router = APIRouter()
Caller = Annotated[CallerSnapshot, Depends(get_filesystem_caller)]
Sharing = Annotated[FilesystemSharing, Depends(get_filesystem_sharing)]


class ReplaceNodeGroupsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    groups: tuple[GroupPolicy, ...]

    @model_validator(mode="after")
    def unique_groups(self) -> Self:
        if len({group.group_id for group in self.groups}) != len(self.groups):
            raise ValueError("Policy keys must be unique")
        return self


def expected_sharing_revision(request: Request) -> str:
    values = request.headers.getlist("If-Match")
    if not values:
        raise HTTPException(428, detail={
            "code": "filesystem_precondition_required", "message": "If-Match is required.",
        })
    if (
        len(values) != 1
        or re.fullmatch(r'"[\x21\x23-\x2b\x2d-\x7e]+"', values[0]) is None
        or values[0][1:-1].isdigit()
    ):
        raise HTTPException(422, detail=[{
            "loc": ["header", "If-Match"], "type": "value_error",
            "msg": "Expected one strong quoted opaque sharing revision.",
        }])
    return values[0][1:-1]


@router.get("/nodes/{node_id}/access/eligible-groups", response_model=EligibleSharingGroups)
async def eligible_groups(
    node_id: UUID, caller: Caller, sharing: Sharing,
) -> EligibleSharingGroups:
    with filesystem_errors():
        return await sharing.eligible_groups(caller, node_id)


@router.get("/nodes/{node_id}/access", response_model=NodeGroupPolicyView)
async def inspect_access(
    node_id: UUID, caller: Caller, sharing: Sharing, response: Response,
) -> NodeGroupPolicyView:
    with filesystem_errors():
        view = await sharing.inspect(caller, node_id)
    response.headers["ETag"] = f'"{view.revision}"'
    return view


@router.put(
    "/nodes/{node_id}/access", response_model=NodeGroupPolicyView,
    openapi_extra={"parameters": [{
        "name": "If-Match", "in": "header", "required": True,
        "schema": {"type": "string"},
        "description": "One strong quoted opaque sharing revision, not a node content revision.",
    }]},
    responses={
        403: {"description": "Missing, undiscoverable or unauthorized node."},
        412: {"description": "Sharing revision no longer matches If-Match."},
        428: {"description": "If-Match is required."},
    },
)
async def replace_access(
    node_id: UUID, body: ReplaceNodeGroupsRequest, caller: Caller, sharing: Sharing,
    response: Response, revision: Annotated[str, Depends(expected_sharing_revision)],
) -> NodeGroupPolicyView:
    with filesystem_errors():
        view = await sharing.replace(caller, node_id, ReplaceNodeGroupPolicy(
            expected_revision=revision, groups=body.groups,
        ))
    response.headers["ETag"] = f'"{view.revision}"'
    return view
