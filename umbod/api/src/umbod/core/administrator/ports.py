from typing import Protocol

from umbod.core.groups.models import Group
from umbod.core.identity_directory.models import DirectoryScope, UserPage
from umbod.core.permissions.domain import (
    AssignablePermissionTargets,
    PermissionChangeResult,
    UpdateGroupPermissionsRequest,
)


from .models import ConnectorInventoryEntry


class ConnectorInventory(Protocol):
    async def list_connectors(self) -> tuple[ConnectorInventoryEntry, ...]: ...


class RegisteredGroupReader(Protocol):
    async def list_groups(self) -> tuple[Group, ...]: ...


class AssignableTargetReader(Protocol):
    async def list_assignable_targets(self) -> AssignablePermissionTargets: ...


class ObservedUserSearch(Protocol):
    async def search_users(self, scope: DirectoryScope) -> UserPage: ...


class GroupPermissionPatcher(Protocol):
    async def update_group_permissions(
        self, request: UpdateGroupPermissionsRequest
    ) -> PermissionChangeResult: ...
