import json
from importlib import import_module
from typing import Any

from umbod.core.callers import GroupMembership

import pytest

from umbod.mcp.live_permission_updates import (
    PermissionRuntimeSyncResult,
    RuntimeGroupPermissionSynchronizer,
)
from umbod.core.permissions import ConnectorToolRef as PermissionToolRef
from umbod.core.permissions import GroupPermissionSet
from umbod.core.permissions import (
    ConnectorToolPermission,
    InMemoryGroupConnectorToolPermissions,
)


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
    membership = GroupMembership(group_ids=("engineering",))

    await reloader.reload_group_permissions()

    _assert_engineering_can_see_github_create_issue(permissions, membership)

    reader.permission_sets = (_empty_engineering_permissions(),)
    await reloader.reload_group_permissions()

    _assert_engineering_cannot_see_github_create_issue(permissions, membership)


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
    membership: GroupMembership,
) -> None:
    assert permissions.allowed_connector_ids(membership) == {"github"}
    assert permissions.allowed_tools(membership) == {
        ConnectorToolPermission(connector_id="github", operation_name="create_issue")
    }


def _assert_engineering_cannot_see_github_create_issue(
    permissions: InMemoryGroupConnectorToolPermissions,
    membership: GroupMembership,
) -> None:
    assert permissions.allowed_connector_ids(membership) == set()
    assert permissions.allowed_tools(membership) == set()


@pytest.mark.asyncio
async def test_live_permission_update_reloads_latest_known_state_and_notifies_clients() -> None:
    reloader = RecordingPermissionStateReloader(applied_latest_state=False, fail=False)
    notifier = RecordingToolListChangeNotifier(notifications=0, notify_result=True)
    synchronizer = RuntimeGroupPermissionSynchronizer(permission_state_reloader=reloader, client_notifier=notifier)

    result = await synchronizer.sync_group_permissions()

    assert result.latest_known_state_applied is True
    assert result.clients_notified is True
    assert reloader.applied_latest_state is True
    assert notifier.notifications == 1


@pytest.mark.asyncio
async def test_runtime_does_not_notify_clients_when_latest_known_state_cannot_be_applied() -> None:
    reloader = RecordingPermissionStateReloader(applied_latest_state=False, fail=True)
    notifier = RecordingToolListChangeNotifier(notifications=0, notify_result=True)
    synchronizer = RuntimeGroupPermissionSynchronizer(permission_state_reloader=reloader, client_notifier=notifier)

    with pytest.raises(RuntimeError, match="permission state unavailable"):
        await synchronizer.sync_group_permissions()

    assert reloader.applied_latest_state is False
    assert notifier.notifications == 0


@pytest.mark.asyncio
async def test_runtime_catch_up_applies_latest_known_state_and_notifies_clients() -> None:
    reloader = RecordingPermissionStateReloader(applied_latest_state=False, fail=False)
    notifier = RecordingToolListChangeNotifier(notifications=0, notify_result=True)
    synchronizer = RuntimeGroupPermissionSynchronizer(permission_state_reloader=reloader, client_notifier=notifier)

    result = await synchronizer.sync_group_permissions()

    assert result == PermissionRuntimeSyncResult(
        latest_known_state_applied=True, clients_notified=True
    )
    assert reloader.applied_latest_state is True
    assert notifier.notifications == 1
