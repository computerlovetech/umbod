import json
from importlib import import_module
from typing import Any

import pytest

from umbod.mcp.live_permission_updates import (
    GroupPermissionChangePollingSynchronizer,
    GroupPermissionChanged,
    InMemoryGroupPermissionChangeEventStream,
    PermissionRuntimeSyncResult,
    RuntimeGroupPermissionSynchronizer,
)
from umbod.core.permissions import ConnectorToolRef as PermissionToolRef
from umbod.core.permissions import GroupPermissionSet
from umbod.core.permissions import (
    ConnectorToolPermission,
    InMemoryGroupConnectorToolPermissions,
)
from umbod.core.permissions import ConnectorToolRef
from messaging.events import McpGroupPermissionChanged
from messaging.models import StreamEvent


class RecordingGroupPermissionReader:
    def __init__(self, permission_sets: tuple[GroupPermissionSet, ...]) -> None:
        self.permission_sets = permission_sets

    async def list_group_permissions(self, group_id: str) -> GroupPermissionSet:
        for permission_set in self.permission_sets:
            if permission_set.group_id == group_id:
                return permission_set
        return GroupPermissionSet(group_id=group_id, connector_ids=(), capabilities=())

    async def list_all_group_permissions(self) -> tuple[GroupPermissionSet, ...]:
        return self.permission_sets


class LiveRuntimePermissionUpdateDsl:
    def __init__(
        self,
        stream: InMemoryGroupPermissionChangeEventStream,
        synchronizer: RuntimeGroupPermissionSynchronizer,
    ) -> None:
        self.stream = stream
        self.synchronizer = synchronizer

    async def publish_group_permission_changed(
        self,
        event: GroupPermissionChanged,
    ) -> object:
        return await self.stream.append_group_permission_changed(event)

    async def apply_live_permission_updates(self) -> PermissionRuntimeSyncResult:
        return await self.synchronizer.sync_group_permissions()

    async def catch_up_permission_updates(self) -> PermissionRuntimeSyncResult:
        return await self.synchronizer.sync_group_permissions()


class RecordingPermissionStateReloader:
    def __init__(self, applied_latest_state: bool, fail: bool) -> None:
        self.applied_latest_state = applied_latest_state
        self.fail = fail

    async def reload_group_permissions(self) -> bool:
        if self.fail:
            raise RuntimeError("permission state unavailable")
        self.applied_latest_state = True
        return True


class RecordingToolListChangeNotifier:
    def __init__(self, notifications: int, notify_result: bool) -> None:
        self.notifications = notifications
        self.notify_result = notify_result

    def notify_tool_list_changed(self) -> bool:
        self.notifications += 1
        return self.notify_result

    def notify_prompt_list_changed(self) -> bool:
        return self.notify_result

    def notify_resource_list_changed(self) -> bool:
        return self.notify_result


class RecordingMcpGroupPermissionStreamReader:
    def __init__(self, events: list[StreamEvent]) -> None:
        self.events = events
        self.calls: list[tuple[int, int]] = []

    async def list_after(self, sequence: int, limit: int) -> list[StreamEvent]:
        self.calls.append((sequence, limit))
        return [event for event in self.events if event.sequence > sequence][:limit]


class RecordingCheckpointStore:
    def __init__(self) -> None:
        self.sequence = 0
        self.saved_sequences: list[tuple[str, int]] = []

    async def get_last_processed_sequence(self, consumer_id: str) -> int:
        return self.sequence

    async def save_last_processed_sequence(self, consumer_id: str, sequence: int) -> None:
        self.sequence = sequence
        self.saved_sequences.append((consumer_id, sequence))


class RecordingRuntimeGroupPermissionSynchronizer:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.sync_calls = 0

    async def sync_group_permissions(self) -> PermissionRuntimeSyncResult:
        self.sync_calls += 1
        if self.fail:
            raise RuntimeError("permission sync failed")
        return PermissionRuntimeSyncResult(latest_known_state_applied=True, clients_notified=True)


@pytest.mark.asyncio
async def test_group_permission_change_polling_reads_after_checkpoint_syncs_and_checkpoints() -> (
    None
):
    checkpoint_store = RecordingCheckpointStore()
    synchronizer = RecordingRuntimeGroupPermissionSynchronizer(fail=False)
    stream_reader = RecordingMcpGroupPermissionStreamReader(
        events=[_mcp_group_permission_stream_event(sequence=1, group_id="engineering")]
    )
    polling_synchronizer = GroupPermissionChangePollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=stream_reader,
        runtime_synchronizer=synchronizer,
        interval_seconds=5.0,
        batch_limit=100,
    )

    await polling_synchronizer.poll_once()

    assert stream_reader.calls == [(0, 100)]
    assert synchronizer.sync_calls == 1
    assert checkpoint_store.saved_sequences == [("consumer", 1)]
    assert checkpoint_store.sequence == 1


@pytest.mark.asyncio
async def test_group_permission_change_polling_does_not_checkpoint_when_sync_fails() -> None:
    checkpoint_store = RecordingCheckpointStore()
    synchronizer = RecordingRuntimeGroupPermissionSynchronizer(fail=True)
    stream_reader = RecordingMcpGroupPermissionStreamReader(
        events=[_mcp_group_permission_stream_event(sequence=1, group_id="support")]
    )
    polling_synchronizer = GroupPermissionChangePollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=stream_reader,
        runtime_synchronizer=synchronizer,
        interval_seconds=5.0,
        batch_limit=100,
    )

    with pytest.raises(RuntimeError, match="permission sync failed"):
        await polling_synchronizer.poll_once()

    assert stream_reader.calls == [(0, 100)]
    assert synchronizer.sync_calls == 1
    assert checkpoint_store.saved_sequences == []
    assert checkpoint_store.sequence == 0


@pytest.mark.asyncio
async def test_group_tool_grant_event_is_published_as_metadata_only_event() -> None:
    stream = InMemoryGroupPermissionChangeEventStream()
    tool = ConnectorToolRef(connector_id="github", operation_name="create_issue")
    dsl = LiveRuntimePermissionUpdateDsl(
        stream=stream,
        synchronizer=RuntimeGroupPermissionSynchronizer(
            permission_state_reloader=RecordingPermissionStateReloader(
                applied_latest_state=False, fail=False
            ),
            client_notifier=RecordingToolListChangeNotifier(notifications=0, notify_result=True),
        ),
    )

    stream_event = await dsl.publish_group_permission_changed(
        GroupPermissionChanged(
            group_id="engineering",
            action="grant",
            target_kind="tool",
            connector_id="github",
            capability=tool.as_capability(),
        )
    )

    assert stream_event.sequence == 1
    assert stream_event.event.group_id == "engineering"
    assert stream_event.event.action == "grant"
    assert stream_event.event.target_kind == "tool"
    assert stream_event.event.connector_id == "github"
    assert stream_event.event.capability == tool.as_capability()
    assert not hasattr(stream_event.event, "permission_snapshot")


@pytest.mark.asyncio
async def test_group_connector_revoke_event_can_be_read_for_runtime_catch_up() -> None:
    stream = InMemoryGroupPermissionChangeEventStream()
    dsl = LiveRuntimePermissionUpdateDsl(
        stream=stream,
        synchronizer=RuntimeGroupPermissionSynchronizer(
            permission_state_reloader=RecordingPermissionStateReloader(
                applied_latest_state=False, fail=False
            ),
            client_notifier=RecordingToolListChangeNotifier(notifications=0, notify_result=True),
        ),
    )

    await dsl.publish_group_permission_changed(
        GroupPermissionChanged(
            group_id="support",
            action="revoke",
            target_kind="connector",
            connector_id="zendesk",
        )
    )

    events = await stream.list_group_permission_changed_after(sequence=0, limit=10)

    assert len(events) == 1
    assert events[0].sequence == 1
    assert events[0].event.group_id == "support"
    assert events[0].event.action == "revoke"
    assert events[0].event.target_kind == "connector"
    assert events[0].event.connector_id == "zendesk"


@pytest.mark.asyncio
async def test_group_permission_state_reloader_refreshes_runtime_permissions_for_filtering_and_direct_calls() -> (
    None
):
    reader = RecordingGroupPermissionReader(permission_sets=(_engineering_github_permissions(),))
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    module = import_module("umbod.mcp.live_permission_updates")
    reloader = module.GroupPermissionStateReloader(
        permission_reader=reader, runtime_permissions=permissions
    )
    jwt_claims = {"groups": ["engineering"]}

    await reloader.reload_group_permissions()

    _assert_engineering_can_see_github_create_issue(permissions, jwt_claims)

    reader.permission_sets = (_empty_engineering_permissions(),)
    await reloader.reload_group_permissions()

    _assert_engineering_cannot_see_github_create_issue(permissions, jwt_claims)


@pytest.mark.asyncio
async def test_http_group_permission_reader_lists_all_group_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("umbod.mcp.live_permission_updates")
    monkeypatch.setattr(module, "urlopen", _group_permissions_urlopen, raising=False)
    reader = module.HttpGroupPermissionReader(api_base_url="http://api.test/system")

    permission_sets = await reader.list_all_group_permissions()

    assert permission_sets == (
        GroupPermissionSet(
            group_id="engineering",
            connector_ids=("github",),
            capabilities=(PermissionToolRef(connector_id="github", operation_name="create_issue").as_capability(),),
        ),
    )


def _group_permissions_urlopen(url: str, timeout: int) -> "JsonResponse":
    assert url == "http://api.test/system/mcp-permissions/groups"
    assert timeout == 10
    return JsonResponse(
        {
            "groups": [
                {
                    "group_id": "engineering",
                    "connector_ids": ["github"],
                    "capabilities": [{"connector_id": "github", "capability_kind": "tool", "capability_key": "create_issue"}],
                }
            ]
        }
    )


class JsonResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "JsonResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _mcp_group_permission_stream_event(sequence: int, group_id: str) -> StreamEvent:
    return StreamEvent(
        sequence=sequence,
        event=McpGroupPermissionChanged(
            group_id=group_id,
            action="grant",
            target_kind="connector",
            connector_id="github",
        ).to_messaging_event(),
    )


def _engineering_github_permissions() -> GroupPermissionSet:
    return GroupPermissionSet(
        group_id="engineering",
        connector_ids=("github",),
        capabilities=(PermissionToolRef(connector_id="github", operation_name="create_issue").as_capability(),),
    )


def _empty_engineering_permissions() -> GroupPermissionSet:
    return GroupPermissionSet(group_id="engineering", connector_ids=(), capabilities=())


def _assert_engineering_can_see_github_create_issue(
    permissions: InMemoryGroupConnectorToolPermissions,
    jwt_claims: dict[str, list[str]],
) -> None:
    assert permissions.allowed_connector_ids(jwt_claims) == {"github"}
    assert permissions.allowed_tools(jwt_claims) == {
        ConnectorToolPermission(connector_id="github", operation_name="create_issue")
    }


def _assert_engineering_cannot_see_github_create_issue(
    permissions: InMemoryGroupConnectorToolPermissions,
    jwt_claims: dict[str, list[str]],
) -> None:
    assert permissions.allowed_connector_ids(jwt_claims) == set()
    assert permissions.allowed_tools(jwt_claims) == set()


@pytest.mark.asyncio
async def test_live_permission_update_reloads_latest_known_state_and_notifies_clients() -> None:
    reloader = RecordingPermissionStateReloader(applied_latest_state=False, fail=False)
    notifier = RecordingToolListChangeNotifier(notifications=0, notify_result=True)
    dsl = LiveRuntimePermissionUpdateDsl(
        stream=InMemoryGroupPermissionChangeEventStream(),
        synchronizer=RuntimeGroupPermissionSynchronizer(
            permission_state_reloader=reloader,
            client_notifier=notifier,
        ),
    )

    result = await dsl.apply_live_permission_updates()

    assert result.latest_known_state_applied is True
    assert result.clients_notified is True
    assert reloader.applied_latest_state is True
    assert notifier.notifications == 1


@pytest.mark.asyncio
async def test_runtime_does_not_notify_clients_when_latest_known_state_cannot_be_applied() -> None:
    reloader = RecordingPermissionStateReloader(applied_latest_state=False, fail=True)
    notifier = RecordingToolListChangeNotifier(notifications=0, notify_result=True)
    dsl = LiveRuntimePermissionUpdateDsl(
        stream=InMemoryGroupPermissionChangeEventStream(),
        synchronizer=RuntimeGroupPermissionSynchronizer(
            permission_state_reloader=reloader,
            client_notifier=notifier,
        ),
    )

    with pytest.raises(RuntimeError, match="permission state unavailable"):
        await dsl.apply_live_permission_updates()

    assert reloader.applied_latest_state is False
    assert notifier.notifications == 0


@pytest.mark.asyncio
async def test_runtime_catch_up_applies_latest_known_state_and_notifies_clients() -> None:
    reloader = RecordingPermissionStateReloader(applied_latest_state=False, fail=False)
    notifier = RecordingToolListChangeNotifier(notifications=0, notify_result=True)
    dsl = LiveRuntimePermissionUpdateDsl(
        stream=InMemoryGroupPermissionChangeEventStream(),
        synchronizer=RuntimeGroupPermissionSynchronizer(
            permission_state_reloader=reloader,
            client_notifier=notifier,
        ),
    )

    result = await dsl.catch_up_permission_updates()

    assert result == PermissionRuntimeSyncResult(
        latest_known_state_applied=True, clients_notified=True
    )
    assert reloader.applied_latest_state is True
    assert notifier.notifications == 1
