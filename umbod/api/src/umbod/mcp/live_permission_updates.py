import asyncio
import json
import logging

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import TypeAdapter

from umbod.core.permissions import ConnectorCapabilityRef as PermissionConnectorCapabilityRef
from umbod.core.permissions import (
    GroupPermissionReader,
    GroupPermissionSet,
    GroupPermissionSummary,
)
from messaging.models import StreamEvent
from umbod.core.permissions import (
    ConnectorCapabilityPermission,
    InMemoryGroupConnectorToolPermissions,
)

PermissionChangeAction = Literal["grant", "revoke"]
PermissionTargetKind = Literal[
    "connector", "tool", "prompt", "resource", "resource_template", "capability"
]
GROUP_PERMISSION_CHANGE_POLL_INTERVAL_SECONDS = 5.0
GROUP_PERMISSION_CHANGE_POLL_BATCH_LIMIT = 100

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupPermissionChanged:
    group_id: str
    action: PermissionChangeAction
    target_kind: PermissionTargetKind
    connector_id: str
    capability: PermissionConnectorCapabilityRef | None = None


@dataclass(frozen=True)
class GroupPermissionChangedStreamEvent:
    sequence: int
    event: GroupPermissionChanged


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


class GroupPermissionChangeEventCheckpointStore(Protocol):
    async def get_last_processed_sequence(self, consumer_id: str) -> int: ...

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None: ...


class GroupPermissionChangeStreamReader(Protocol):
    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]: ...


class GroupPermissionRuntimeSynchronizer(Protocol):
    async def sync_group_permissions(self) -> PermissionRuntimeSyncResult: ...


class GroupPermissionChangePollingSynchronizer:
    def __init__(
        self,
        *,
        consumer_id: str,
        checkpoint_store: GroupPermissionChangeEventCheckpointStore,
        stream_reader: GroupPermissionChangeStreamReader,
        runtime_synchronizer: GroupPermissionRuntimeSynchronizer,
        interval_seconds: float,
        batch_limit: int,
    ) -> None:
        self._consumer_id = consumer_id
        self._checkpoint_store = checkpoint_store
        self._stream_reader = stream_reader
        self._runtime_synchronizer = runtime_synchronizer
        self._interval_seconds = float(interval_seconds)
        self._batch_limit = batch_limit
        self._stopped = asyncio.Event()

    async def poll_once(self) -> None:
        sequence = await self._checkpoint_store.get_last_processed_sequence(self._consumer_id)
        events = await self._stream_reader.list_after(sequence, self._batch_limit)
        for stream_event in events:
            await self._runtime_synchronizer.sync_group_permissions()
            await self._checkpoint_store.save_last_processed_sequence(
                self._consumer_id, stream_event.sequence
            )

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Group permission synchronization failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()


class HttpGroupPermissionChangeStreamReader:
    def __init__(self, api_base_url: str) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._events_adapter = TypeAdapter(list[StreamEvent])

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        return await asyncio.to_thread(self._list_after_sync, sequence, limit)

    def _list_after_sync(self, sequence: int, limit: int) -> list[StreamEvent]:
        query = urlencode(
            {
                "after_sequence": sequence,
                "limit": limit,
                "event_type": "mcp.group_permission.changed",
            }
        )
        url = f"{self._api_base_url}/system/events?{query}"
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self._events_adapter.validate_python(payload)


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


class InMemoryGroupPermissionChangeEventStream:
    def __init__(self) -> None:
        self._events: list[GroupPermissionChangedStreamEvent] = []

    async def append_group_permission_changed(
        self,
        event: GroupPermissionChanged,
    ) -> GroupPermissionChangedStreamEvent:
        stream_event = GroupPermissionChangedStreamEvent(
            sequence=len(self._events) + 1,
            event=event,
        )
        self._events.append(stream_event)
        return stream_event

    async def list_group_permission_changed_after(
        self,
        sequence: int,
        limit: int,
    ) -> tuple[GroupPermissionChangedStreamEvent, ...]:
        if limit <= 0:
            return ()
        matching_events = [event for event in self._events if event.sequence > sequence]
        return tuple(matching_events[:limit])


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
