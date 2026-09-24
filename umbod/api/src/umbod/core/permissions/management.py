from umbod.core.permissions.domain import (
    GroupPermissionSet,
    GroupPermissionSummary,
    PermissionChangeResult,
    SaveGroupPermissionsRequest,
    UpdateGroupPermissionsRequest,
)
from umbod.core.permissions.ports import (
    ConnectorCapabilityPermissionCatalog,
    PermissionChangeNotifier,
)
from umbod.core.permissions.ports import GroupPermissionStore


class GroupPermissionManagementService:
    def __init__(
        self,
        store: GroupPermissionStore,
        catalog: ConnectorCapabilityPermissionCatalog,
        notifier: PermissionChangeNotifier,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._notifier = notifier

    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]:
        return await self._store.list_group_identifiers()

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        return await self._store.list_group_permissions(group_id)

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        return await self._store.list_all_group_permissions()

    async def register_permission_group(self, group_id: str) -> PermissionChangeResult:
        if not group_id.strip():
            return PermissionChangeResult(
                status="rejected", group_id=group_id, message="Group ID must not be empty"
            )
        await self._store.register_group(group_id)
        return self._applied(group_id)

    async def delete_permission_group(self, group_id: str) -> PermissionChangeResult:
        permission_set = await self._store.list_group_permissions(group_id)
        if permission_set.connector_ids or permission_set.capabilities:
            return PermissionChangeResult(
                status="rejected",
                group_id=group_id,
                message="Remove connector and capability permissions before deleting this group.",
            )
        await self._store.delete_group(group_id)
        return self._applied(group_id)

    async def save_group_permissions(
        self, request: SaveGroupPermissionsRequest
    ) -> PermissionChangeResult:
        for connector_id in request.connector_ids:
            if not await self._catalog.has_connector(connector_id):
                return PermissionChangeResult(
                    status="rejected", group_id=request.group_id, message="Unknown connector"
                )
        for capability in request.capabilities:
            if not await self._catalog.has_capability(capability):
                return PermissionChangeResult(
                    status="rejected",
                    group_id=request.group_id,
                    message="Unknown connector capability",
                )
        await self._store.save_group_permissions(request)
        return self._applied(request.group_id)

    async def update_group_permissions(
        self, request: UpdateGroupPermissionsRequest
    ) -> PermissionChangeResult:
        for connector in request.connectors:
            if connector.permission_status == "enabled" and not await self._catalog.has_connector(
                connector.connector_id
            ):
                return PermissionChangeResult(
                    status="rejected", group_id=request.group_id, message="Unknown connector"
                )
        for capability in request.capabilities:
            if capability.permission_status == "enabled" and not await self._catalog.has_capability(
                capability.capability
            ):
                return PermissionChangeResult(
                    status="rejected",
                    group_id=request.group_id,
                    message="Unknown connector capability",
                )
        await self._store.update_group_permissions(request)
        return self._applied(request.group_id)

    def _applied(self, group_id: str) -> PermissionChangeResult:
        return PermissionChangeResult(
            status="applied",
            group_id=group_id,
            clients_notified=self._notifier.permissions_changed(),
        )


AdminGroupPermissionManagement = GroupPermissionManagementService
