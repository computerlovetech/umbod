from fastapi import HTTPException

from umbod.rest.mcp_permissions.schemas import (
    AssignableCapabilityPermissionTargetResponse,
    AssignableConnectorPermissionTargetResponse,
    AssignablePermissionTargetsResponse,
    ConnectorCapabilityPermissionResponse,
    GroupPermissionResponse,
    PermissionChangeResponse,
    UpdateGroupPermissionsApiRequest,
)
from umbod.core.permissions import (
    AssignablePermissionTargets,
    CapabilityPermissionUpdate,
    ConnectorCapabilityRef,
    ConnectorPermissionUpdate,
    GroupPermissionSet,
    PermissionChangeResult,
    UpdateGroupPermissionsRequest,
)


def assignable_permission_targets_response(
    targets: AssignablePermissionTargets,
) -> AssignablePermissionTargetsResponse:
    return AssignablePermissionTargetsResponse(
        connectors=[
            AssignableConnectorPermissionTargetResponse(
                connector_id=connector.connector_id,
                display_name=connector.display_name,
            )
            for connector in targets.connectors
        ],
        capabilities=[
            AssignableCapabilityPermissionTargetResponse(
                connector_id=capability.connector_id,
                capability_kind=capability.capability_kind,
                capability_key=capability.capability_key,
                display_name=capability.display_name,
            )
            for capability in targets.capabilities
        ],
    )


def group_permission_response(permission_set: GroupPermissionSet) -> GroupPermissionResponse:
    return GroupPermissionResponse(
        group_id=permission_set.group_id,
        connector_ids=list(permission_set.connector_ids),
        capabilities=[
            ConnectorCapabilityPermissionResponse(
                connector_id=capability.connector_id,
                capability_kind=capability.capability_kind,
                capability_key=capability.capability_key,
            )
            for capability in permission_set.capabilities
        ],
    )


def permission_change_response(result: PermissionChangeResult) -> PermissionChangeResponse:
    return PermissionChangeResponse(
        status=result.status,
        group_id=result.group_id,
        message=result.message,
        clients_notified=result.clients_notified,
    )


def update_group_permissions_request(
    group_id: str, request: UpdateGroupPermissionsApiRequest
) -> UpdateGroupPermissionsRequest:
    return UpdateGroupPermissionsRequest(
        group_id=group_id,
        connectors=tuple(
            ConnectorPermissionUpdate(
                connector_id=connector.connector_id,
                permission_status=connector.permission_status,
            )
            for connector in request.connectors
        ),
        capabilities=tuple(
            CapabilityPermissionUpdate(
                capability=ConnectorCapabilityRef(
                    connector_id=item.connector_id,
                    capability_kind=item.capability_kind,
                    capability_key=item.capability_key,
                ),
                permission_status=item.permission_status,
            )
            for item in request.capabilities
        ),
    )


def permission_change_or_not_found(result: PermissionChangeResult) -> PermissionChangeResponse:
    if result.status == "rejected":
        raise HTTPException(
            status_code=404, detail=result.message or "Permission target was not found"
        )
    return permission_change_response(result)
