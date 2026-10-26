from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from umbod.core.groups import Group, GroupInUse, GroupManagementService, RegisterGroup
from .deps import get_group_management


class GroupListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    groups: tuple[Group, ...]


router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("")
async def list_groups(
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> GroupListResponse:
    return GroupListResponse(groups=await management.list_groups())


@router.post("", status_code=204)
async def register_group(
    request: RegisterGroup,
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> Response:
    await management.register_group(request)
    return Response(status_code=204)


@router.delete("", status_code=204)
async def delete_group_request(
    request: Group,
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> Response:
    return await delete_group(request.group_id, management)


@router.delete("/{group_id:path}", status_code=204)
async def delete_group(
    group_id: str,
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> Response:
    try:
        await management.delete_group(group_id)
    except GroupInUse as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=204)
