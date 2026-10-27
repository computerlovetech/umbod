from messaging.events import McpGroupPermissionChanged
from umbod.core.messaging.stores.event_stream import append_event_in_session
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.groups.stores.registration import register_group_in_session
from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.permissions.domain import (
    CapabilityPermissionUpdate,
    ConnectorCapabilityRef,
    ConnectorPermissionUpdate,
    GroupPermissionSet,
    GroupPermissionSummary,
    SaveGroupPermissionsRequest,
    UpdateGroupPermissionsRequest,
    _capability_sort_key,
)
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_CONNECTOR_ID,
    CAPABILITY_PERMISSION_GROUP_ID,
    CAPABILITY_PERMISSION_KEY,
    CAPABILITY_PERMISSION_KIND,
    CONNECTOR_CAPABILITY_PROJECTION,
    CONNECTOR_ID_PROJECTION,
    CONNECTOR_PERMISSION_CONNECTOR_ID,
    CONNECTOR_PERMISSION_GROUP_ID,
    GroupCapabilityPermissionKey,
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionKey,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence.ports import Database, DatabaseSession, TransactionMode
from umbod.core.persistence.query import (
    AllOf,
    DeleteQuery,
    Equals,
    InsertCommand,
    OrderBy,
    Query,
    Table,
)


class GroupPermissionStoreService:
    def __init__(
        self,
        database: Database,
        connector_permissions: Table[GroupConnectorPermissionRecord, GroupConnectorPermissionKey],
        capability_permissions: Table[
            GroupCapabilityPermissionRecord, GroupCapabilityPermissionKey
        ],
    ) -> None:
        self._database = database
        self._connector_permissions = connector_permissions
        self._capability_permissions = capability_permissions

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            return await self.list_group_permissions_in_session(session, group_id)

    async def list_group_permissions_in_session(
        self, session: DatabaseSession, group_id: str
    ) -> GroupPermissionSet:
        connector_ids = tuple(
            row.connector_id
            for row in await session.find_many(
                self._connector_permissions,
                Query(
                    filter=Equals(CONNECTOR_PERMISSION_GROUP_ID, group_id),
                    projection=CONNECTOR_ID_PROJECTION,
                    ordering=OrderBy((CONNECTOR_PERMISSION_CONNECTOR_ID,)),
                ),
            )
        )
        capabilities = tuple(
            ConnectorCapabilityRef(
                connector_id=row.connector_id,
                capability_kind=_capability_kind(row.capability_kind),
                capability_key=row.capability_key,
            )
            for row in await session.find_many(
                self._capability_permissions,
                Query(
                    filter=Equals(CAPABILITY_PERMISSION_GROUP_ID, group_id),
                    projection=CONNECTOR_CAPABILITY_PROJECTION,
                    ordering=OrderBy(
                        (
                            CAPABILITY_PERMISSION_CONNECTOR_ID,
                            CAPABILITY_PERMISSION_KIND,
                            CAPABILITY_PERMISSION_KEY,
                        )
                    ),
                ),
            )
        )
        return GroupPermissionSet(
            group_id=group_id, connector_ids=connector_ids, capabilities=capabilities
        )

    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]:
        groups = await create_group_management(self._database).list_groups()
        return tuple(GroupPermissionSummary(group_id=group.group_id) for group in groups)

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        permission_sets = []
        for summary in await self.list_group_identifiers():
            permission_sets.append(await self.list_group_permissions(summary.group_id))
        return tuple(permission_sets)

    async def register_group(self, group_id: str) -> None:
        await create_group_management(self._database).register_group(RegisterGroup(group_id=group_id))

    async def delete_group(self, group_id: str) -> None:
        await create_group_management(self._database).delete_group(group_id)

    async def update_group_permissions(self, request: UpdateGroupPermissionsRequest) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            previous = await self.list_group_permissions_in_session(session, request.group_id)
            await self.update_group_permissions_in_session(session, request)
            current = await self.list_group_permissions_in_session(session, request.group_id)
            await _append_permission_changes(session, previous, current)

    async def update_group_permissions_in_session(
        self,
        session: DatabaseSession,
        request: UpdateGroupPermissionsRequest,
    ) -> None:
        await register_group_in_session(session, request.group_id)
        for connector in request.connectors:
            await self._update_connector_permission(session, request.group_id, connector)
        for capability in request.capabilities:
            await self._update_capability_permission(session, request.group_id, capability)

    async def save_group_permissions(self, request: SaveGroupPermissionsRequest) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            previous = await self.list_group_permissions_in_session(session, request.group_id)
            await register_group_in_session(session, request.group_id)
            await session.delete(
                self._connector_permissions,
                DeleteQuery(Equals(CONNECTOR_PERMISSION_GROUP_ID, request.group_id)),
            )
            await session.delete(
                self._capability_permissions,
                DeleteQuery(Equals(CAPABILITY_PERMISSION_GROUP_ID, request.group_id)),
            )
            for connector_id in sorted(request.connector_ids):
                await self._insert_connector_permission(session, request.group_id, connector_id)
            for capability in sorted(request.capabilities, key=_capability_sort_key):
                await self._insert_capability_permission(session, request.group_id, capability)
            current = await self.list_group_permissions_in_session(session, request.group_id)
            await _append_permission_changes(session, previous, current)

    async def _update_connector_permission(
        self,
        session: DatabaseSession,
        group_id: str,
        update: ConnectorPermissionUpdate,
    ) -> None:
        query = DeleteQuery(
            AllOf(
                (
                    Equals(CONNECTOR_PERMISSION_GROUP_ID, group_id),
                    Equals(CONNECTOR_PERMISSION_CONNECTOR_ID, update.connector_id),
                )
            )
        )
        await session.delete(self._connector_permissions, query)
        if update.permission_status == "enabled":
            await self._insert_connector_permission(session, group_id, update.connector_id)

    async def _update_capability_permission(
        self, session: DatabaseSession, group_id: str, update: CapabilityPermissionUpdate
    ) -> None:
        query = DeleteQuery(
            AllOf(
                (
                    Equals(CAPABILITY_PERMISSION_GROUP_ID, group_id),
                    Equals(CAPABILITY_PERMISSION_CONNECTOR_ID, update.capability.connector_id),
                    Equals(CAPABILITY_PERMISSION_KIND, update.capability.capability_kind),
                    Equals(CAPABILITY_PERMISSION_KEY, update.capability.capability_key),
                )
            )
        )
        await session.delete(self._capability_permissions, query)
        if update.permission_status == "enabled":
            await self._insert_capability_permission(session, group_id, update.capability)

    async def _insert_connector_permission(
        self, session: DatabaseSession, group_id: str, connector_id: str
    ) -> None:
        await session.insert(
            self._connector_permissions,
            InsertCommand(
                row=GroupConnectorPermissionRecord(group_id=group_id, connector_id=connector_id)
            ),
        )

    async def _insert_capability_permission(
        self, session: DatabaseSession, group_id: str, capability: ConnectorCapabilityRef
    ) -> None:
        await session.insert(
            self._capability_permissions,
            InsertCommand(
                row=GroupCapabilityPermissionRecord(
                    group_id=group_id,
                    connector_id=capability.connector_id,
                    capability_kind=capability.capability_kind,
                    capability_key=capability.capability_key,
                )
            ),
        )


def _capability_kind(value: str) -> CapabilityKind:
    if value not in {"tool", "prompt", "resource", "resource_template"}:
        raise ValueError(f"Unsupported capability kind: {value}")
    return value  # type: ignore[return-value]


async def _append_permission_changes(session: DatabaseSession, previous: GroupPermissionSet, current: GroupPermissionSet) -> None:
    for action, connectors, capabilities in (
        ("grant", set(current.connector_ids) - set(previous.connector_ids), set(current.capabilities) - set(previous.capabilities)),
        ("revoke", set(previous.connector_ids) - set(current.connector_ids), set(previous.capabilities) - set(current.capabilities)),
    ):
        for connector_id in sorted(connectors):
            await append_event_in_session(session, McpGroupPermissionChanged(
                group_id=current.group_id, action=action, target_kind="connector", connector_id=connector_id,
            ).to_messaging_event())
        for capability in sorted(capabilities, key=_capability_sort_key):
            await append_event_in_session(session, McpGroupPermissionChanged(
                group_id=current.group_id, action=action, target_kind=capability.capability_kind,
                connector_id=capability.connector_id, capability_kind=capability.capability_kind,
                capability_key=capability.capability_key,
                operation_name=capability.capability_key if capability.capability_kind == "tool" else None,
            ).to_messaging_event())
