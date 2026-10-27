from umbod.core.persistence import Database
from umbod.core.permissions.factories import create_group_permission_store
import asyncio
import json

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import urlopen


from umbod.core.permissions import ConnectorCapabilityRef as PermissionConnectorCapabilityRef
from umbod.core.permissions import (
    GroupPermissionReader,
    GroupPermissionSet,
    GroupPermissionSummary,
)
from umbod.core.permissions import (
    ConnectorCapabilityPermission,
    InMemoryGroupConnectorToolPermissions,
)

@dataclass(frozen=True)
class PermissionRuntimeSyncResult:
    latest_known_state_applied: bool
    clients_notified: bool


class PermissionStateReloader(Protocol):
    async def reload_group_permissions(self) -> bool: ...


class ToolListChangeNotifier(Protocol):
    def notify_tool_list_changed(self) -> bool: ...

    def notify_prompt_list_changed(self) -> bool: ...

    def notify_resource_list_changed(self) -> bool: ...


class DatabaseGroupPermissionReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]:
        store = await create_group_permission_store(self._database)
        return await store.list_group_identifiers()

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        store = await create_group_permission_store(self._database)
        return await store.list_group_permissions(group_id)

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        store = await create_group_permission_store(self._database)
        return await store.list_all_group_permissions()


class HttpGroupPermissionReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")

    async def list_group_identifiers(self) -> tuple[GroupPermissionSummary, ...]:
        return tuple(
            GroupPermissionSummary(group_id=permission_set.group_id)
            for permission_set in await self.list_all_group_permissions()
        )

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        for permission_set in await self.list_all_group_permissions():
            if permission_set.group_id == group_id:
                return permission_set
        return GroupPermissionSet(group_id=group_id, connector_ids=(), capabilities=())

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        return await asyncio.to_thread(self._list_all_group_permissions_sync)

    def _list_all_group_permissions_sync(self) -> tuple[GroupPermissionSet, ...]:
        url = f"{self._api_base_url}/mcp-permissions/groups"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return tuple(
            self._permission_set_from_payload(group_payload)
            for group_payload in payload.get("groups", [])
        )

    def _permission_set_from_payload(self, payload: dict[str, Any]) -> GroupPermissionSet:
        capabilities = payload.get("capabilities")
        if capabilities is None:
            capabilities = [
                {
                    "connector_id": tool["connector_id"],
                    "capability_kind": "tool",
                    "capability_key": tool["operation_name"],
                }
                for tool in payload.get("tools", [])
            ]
        return GroupPermissionSet(
            group_id=payload["group_id"],
            connector_ids=tuple(payload.get("connector_ids", [])),
            capabilities=tuple(
                PermissionConnectorCapabilityRef(
                    connector_id=item["connector_id"],
                    capability_kind=item["capability_kind"],
                    capability_key=item["capability_key"],
                )
                for item in capabilities
            ),
        )


class GroupPermissionStateReloader:
    def __init__(
        self,
        *,
        permission_reader: GroupPermissionReader,
        runtime_permissions: InMemoryGroupConnectorToolPermissions,
    ) -> None:
        self._permission_reader = permission_reader
        self._runtime_permissions = runtime_permissions

    async def reload_group_permissions(self) -> bool:
        permission_sets = await self._permission_reader.list_all_group_permissions()
        connector_grants_by_group = {
            permission_set.group_id: permission_set.connector_ids
            for permission_set in permission_sets
        }
        capability_grants_by_group = {
            permission_set.group_id: tuple(
                ConnectorCapabilityPermission(
                    connector_id=capability.connector_id,
                    capability_kind=capability.capability_kind,
                    capability_key=capability.capability_key,
                )
                for capability in permission_set.capabilities
            )
            for permission_set in permission_sets
        }
        self._runtime_permissions.replace_group_permissions(
            connector_grants_by_group, capability_grants_by_group
        )
        return True


class RuntimeGroupPermissionSynchronizer:
    def __init__(
        self,
        permission_state_reloader: PermissionStateReloader,
        client_notifier: ToolListChangeNotifier,
    ) -> None:
        self._permission_state_reloader = permission_state_reloader
        self._client_notifier = client_notifier

    async def sync_group_permissions(self) -> PermissionRuntimeSyncResult:
        latest_known_state_applied = (
            await self._permission_state_reloader.reload_group_permissions()
        )
        clients_notified = False
        if latest_known_state_applied:
            tool_notified = self._client_notifier.notify_tool_list_changed()
            prompt_notified = self._client_notifier.notify_prompt_list_changed()
            resource_notified = self._client_notifier.notify_resource_list_changed()
            clients_notified = tool_notified or prompt_notified or resource_notified
        return PermissionRuntimeSyncResult(
            latest_known_state_applied=latest_known_state_applied,
            clients_notified=clients_notified,
        )
