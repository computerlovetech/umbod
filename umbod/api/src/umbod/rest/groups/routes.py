from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, model_validator

from umbod.core.groups import (
    Group, GroupIdentifier, GroupInUse, GroupManagementService, RegisterGroup,
    RegisterGroupMetadata, UpdateGroupMetadata, GroupNotFound, GroupRevisionConflict,
)
from umbod.core.groups.models import GroupLabel, GroupDescription
from .deps import get_group_management


class GroupListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    groups: tuple[Group, ...]


class RegisterGroupRequest(RegisterGroup):
    label: GroupLabel = ""
    description: GroupDescription = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_metadata_label(cls, value: object) -> object:
        if isinstance(value, dict) and "label" not in value and value.get("description"):
            return {**value, "label": value.get("group_id")}
        return value

    def command(self) -> RegisterGroupMetadata | RegisterGroup:
        if "label" not in self.model_fields_set:
            return RegisterGroup(group_id=self.group_id)
        return RegisterGroupMetadata(
            group_id=self.group_id, label=self.label, description=self.description,
        )


class UpdateGroupRequest(UpdateGroupMetadata):
    group_id: str


router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("")
async def list_groups(
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> GroupListResponse:
    return GroupListResponse(groups=await management.list_groups())


@router.post("", status_code=204)
async def register_group(
    request: RegisterGroupRequest,
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> Response:
    command = request.command()
    if isinstance(command, RegisterGroupMetadata):
        await management.register_group_metadata(command)
    else:
        await management.register_group(command)
    return Response(status_code=204)


@router.put("")
async def update_group_request(
    request: UpdateGroupRequest,
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> Group:
    return await update_group(
        request.group_id,
        UpdateGroupMetadata.model_validate(request.model_dump(exclude={"group_id"})),
        management,
    )


@router.put("/{group_id:path}")
async def update_group(
    group_id: str,
    request: UpdateGroupMetadata,
    management: Annotated[GroupManagementService, Depends(get_group_management)],
) -> Group:
    try:
        return await management.update_group_metadata(group_id, request)
    except GroupNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GroupRevisionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("", status_code=204)
async def delete_group_request(
    request: GroupIdentifier,
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
