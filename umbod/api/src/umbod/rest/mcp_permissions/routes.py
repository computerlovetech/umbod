from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from umbod.rest.mcp_permissions.dependencies import (
    get_admin_group_permission_management,
    get_connector_permission_catalog,
    get_mcp_permission_event_publisher,
)
from umbod.rest.mcp_permissions.events import McpPermissionEventPublisher
from umbod.rest.mcp_permissions.mappers import (
    assignable_permission_targets_response,
    group_permission_response,
    permission_change_or_not_found,
    permission_change_response,
    update_group_permissions_request,
)
from umbod.rest.mcp_permissions.schemas import (
    AssignablePermissionTargetsResponse,
    GroupPermissionListResponse,
    GroupPermissionResponse,
    GroupPermissionSummaryResponse,
    PermissionChangeResponse,
    UpdateGroupPermissionsApiRequest,
)
from umbod.core.permissions import (
    AdminGroupPermissionManagement,
    AssignablePermissionCatalog,
)


router = APIRouter(prefix="/mcp-permissions", tags=["mcp-permissions"])


@router.get("/assignable-targets")
async def list_assignable_permission_targets(
    catalog: Annotated[
        AssignablePermissionCatalog, Depends(get_connector_permission_catalog)
    ],
) -> AssignablePermissionTargetsResponse:
    return assignable_permission_targets_response(await catalog.list_assignable_targets())


@router.get("/groups")
async def list_group_permissions(
    management: Annotated[
        AdminGroupPermissionManagement, Depends(get_admin_group_permission_management)
    ],
) -> GroupPermissionListResponse:
    return GroupPermissionListResponse(
        groups=[
            GroupPermissionSummaryResponse(group_id=summary.group_id)
            for summary in await management.list_group_identifiers()
        ]
    )


@router.get("/groups/{group_id}")
async def get_group_permissions(
    group_id: str,
    management: Annotated[
        AdminGroupPermissionManagement, Depends(get_admin_group_permission_management)
    ],
) -> GroupPermissionResponse:
    return group_permission_response(await management.list_group_permissions(group_id))


@router.post("/groups/{group_id}", response_model_exclude_defaults=True)
async def register_permission_group(
    group_id: str,
    management: Annotated[
        AdminGroupPermissionManagement, Depends(get_admin_group_permission_management)
    ],
) -> PermissionChangeResponse:
    result = await management.register_permission_group(group_id)
    if result.status == "rejected":
        raise HTTPException(
            status_code=400, detail=result.message or "Permission group was rejected"
        )
    return permission_change_response(result)


@router.delete("/groups/{group_id}", response_model_exclude_defaults=True)
async def delete_permission_group(
    group_id: str,
    management: Annotated[
        AdminGroupPermissionManagement, Depends(get_admin_group_permission_management)
    ],
) -> PermissionChangeResponse:
    result = await management.delete_permission_group(group_id)
    if result.status == "rejected":
        raise HTTPException(
            status_code=409, detail=result.message or "Permission group deletion was rejected"
        )
    return permission_change_response(result)


@router.put("/groups/{group_id}/permissions", response_model_exclude_defaults=True)
async def update_group_permissions(
    group_id: str,
    request: UpdateGroupPermissionsApiRequest,
    management: Annotated[
        AdminGroupPermissionManagement, Depends(get_admin_group_permission_management)
    ],
    event_publisher: Annotated[
        McpPermissionEventPublisher, Depends(get_mcp_permission_event_publisher)
    ],
) -> PermissionChangeResponse:
    previous_permissions = await management.list_group_permissions(group_id)
    result = await management.update_group_permissions(
        update_group_permissions_request(group_id, request)
    )
    response = permission_change_or_not_found(result)
    next_permissions = await management.list_group_permissions(group_id)
    await event_publisher.publish_saved_permission_changes(previous_permissions, next_permissions)
    return response
