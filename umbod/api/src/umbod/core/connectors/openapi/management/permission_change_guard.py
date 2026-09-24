from umbod.core.connectors.openapi.errors import OpenApiPermissionGrantConflict
from umbod.core.permissions.ports import GroupPermissionReader


class PersistedGroupPermissionActivationChangeGuard:
    def __init__(self, permissions: GroupPermissionReader) -> None:
        self._permissions = permissions

    async def validate_change(
        self,
        connector_id: str,
        previous_operation_ids: frozenset[str],
        next_operation_ids: frozenset[str],
    ) -> None:
        removed_operation_ids = previous_operation_ids - next_operation_ids
        affected_grants = tuple(
            (permission_set.group_id, tool.operation_name)
            for permission_set in await self._permissions.list_all_group_permissions()
            for tool in permission_set.tools
            if tool.connector_id == connector_id and tool.operation_name in removed_operation_ids
        )
        if affected_grants:
            raise OpenApiPermissionGrantConflict(
                connector_id=connector_id,
                removed_operation_ids=tuple(
                    sorted({operation_id for _, operation_id in affected_grants})
                ),
                affected_group_ids=tuple(sorted({group_id for group_id, _ in affected_grants})),
            )
