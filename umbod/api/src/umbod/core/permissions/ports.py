from typing import Protocol

from umbod.core.permissions.domain import (
    AssignablePermissionTargets,
    ConnectorCapabilityRef,
    ConnectorToolRef,
    GroupPermissionSet,
    GroupPermissionSummary,
    SaveGroupPermissionsRequest,
    UpdateGroupPermissionsRequest,
)


class GroupPermissionReader(Protocol):
    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]: ...

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet: ...

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]: ...


class GroupPermissionRegistry(Protocol):
    async def register_group(self, group_id: str) -> None: ...

    async def delete_group(self, group_id: str) -> None: ...


class GroupPermissionSnapshotWriter(Protocol):
    async def save_group_permissions(self, request: SaveGroupPermissionsRequest) -> None: ...

    async def update_group_permissions(self, request: UpdateGroupPermissionsRequest) -> None: ...


class GroupPermissionStore(
    GroupPermissionReader,
    GroupPermissionRegistry,
    GroupPermissionSnapshotWriter,
    Protocol,
):
    pass


class ConnectorCapabilityPermissionCatalog(Protocol):
    async def has_connector(self, connector_id: str) -> bool: ...

    async def has_capability(self, capability: ConnectorCapabilityRef) -> bool: ...

    async def has_tool(self, tool: ConnectorToolRef) -> bool: ...


ConnectorToolPermissionCatalog = ConnectorCapabilityPermissionCatalog


class AssignablePermissionCatalog(ConnectorCapabilityPermissionCatalog, Protocol):
    async def list_assignable_targets(self) -> AssignablePermissionTargets: ...


class PermissionChangeNotifier(Protocol):
    def permissions_changed(self) -> bool: ...
