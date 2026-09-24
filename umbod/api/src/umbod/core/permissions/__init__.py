from typing import TYPE_CHECKING, Any

from umbod.core.permissions.catalog import (
    CapabilityPermissionCatalog,
    CompositeConnectorToolPermissionCatalog,
)
from umbod.core.permissions.domain import (
    AssignableCapabilityPermissionTarget,
    AssignableConnectorPermissionTarget,
    AssignablePermissionTargets,
    CapabilityPermissionUpdate,
    ConnectorCapabilityRef,
    ConnectorPermissionUpdate,
    ConnectorToolRef,
    GroupPermissionSet,
    GroupPermissionSummary,
    PermissionChangeResult,
    PermissionChangeStatus,
    SaveGroupPermissionsRequest,
    ToolPermissionUpdate,
    UpdateGroupPermissionsRequest,
)
from umbod.core.permissions.management import (
    AdminGroupPermissionManagement,
    GroupPermissionManagementService,
)
from umbod.core.permissions.notifier import NoopPermissionChangeNotifier
from umbod.core.permissions.ports import (
    AssignablePermissionCatalog,
    ConnectorCapabilityPermissionCatalog,
    ConnectorToolPermissionCatalog,
    GroupPermissionReader,
    GroupPermissionRegistry,
    GroupPermissionSnapshotWriter,
    GroupPermissionStore,
    PermissionChangeNotifier,
)

AssignableCapabilityPermissionTarget = AssignableCapabilityPermissionTarget

if TYPE_CHECKING:
    from umbod.core.permissions.runtime import (
        ConnectorCapabilityPermission,
        ConnectorToolPermission,
        GroupConnectorToolPermissionState,
        InMemoryGroupConnectorToolPermissions,
        connector_capability_permission_check,
        connector_tool_permission_check,
    )


_RUNTIME_EXPORTS = frozenset(
    {
        "ConnectorCapabilityPermission",
        "ConnectorToolPermission",
        "GroupConnectorToolPermissionState",
        "InMemoryGroupConnectorToolPermissions",
        "connector_capability_permission_check",
        "connector_tool_permission_check",
    }
)


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_EXPORTS:
        from umbod.core.permissions import runtime

        return getattr(runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AdminGroupPermissionManagement",
    "AssignablePermissionCatalog",
    "AssignableCapabilityPermissionTarget",
    "AssignableConnectorPermissionTarget",
    "AssignableCapabilityPermissionTarget",
    "CapabilityPermissionCatalog",
    "AssignablePermissionTargets",
    "CapabilityPermissionUpdate",
    "CompositeConnectorToolPermissionCatalog",
    "ConnectorCapabilityPermission",
    "ConnectorCapabilityPermissionCatalog",
    "ConnectorCapabilityRef",
    "ConnectorToolPermission",
    "ConnectorToolPermissionCatalog",
    "ConnectorPermissionUpdate",
    "ConnectorToolRef",
    "GroupConnectorToolPermissionState",
    "GroupPermissionManagementService",
    "GroupPermissionReader",
    "GroupPermissionRegistry",
    "GroupPermissionSet",
    "GroupPermissionSummary",
    "GroupPermissionSnapshotWriter",
    "GroupPermissionStore",
    "InMemoryGroupConnectorToolPermissions",
    "NoopPermissionChangeNotifier",
    "PermissionChangeNotifier",
    "PermissionChangeResult",
    "PermissionChangeStatus",
    "SaveGroupPermissionsRequest",
    "ToolPermissionUpdate",
    "UpdateGroupPermissionsRequest",
    "connector_capability_permission_check",
    "connector_tool_permission_check",
]
