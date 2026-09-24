from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GROUP_TABLE,
)
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from pathlib import Path
import pytest
import pytest_asyncio
from umbod.core.permissions import (
    AdminGroupPermissionManagement,
    AssignablePermissionCatalog,
    AssignablePermissionTargets,
    CapabilityPermissionUpdate,
    ConnectorCapabilityRef,
    ConnectorPermissionUpdate,
    ConnectorToolRef,
    GroupPermissionManagementService,
    GroupPermissionSet,
    GroupPermissionSummary,
    GroupPermissionStore,
    SaveGroupPermissionsRequest,
    UpdateGroupPermissionsRequest,
)


class AssignablePermissionCatalogFake:
    def __init__(self, connector_tools: dict[str, tuple[str, ...]]) -> None:
        self._connector_tools = connector_tools

    async def has_connector(self, connector_id: str) -> bool:
        return connector_id in self._connector_tools

    async def has_capability(self, capability: ConnectorCapabilityRef) -> bool:
        if capability.capability_kind != "tool":
            return False
        return capability.capability_key in self._connector_tools.get(capability.connector_id, ())

    async def has_tool(self, tool: ConnectorToolRef) -> bool:
        return await self.has_capability(tool.as_capability())

    async def list_assignable_targets(self) -> AssignablePermissionTargets:
        return AssignablePermissionTargets(connectors=(), capabilities=())


class RecordingPermissionChangeNotifier:
    def __init__(self, notify_result: bool) -> None:
        self.notify_result = notify_result
        self.notifications = 0

    def permissions_changed(self) -> bool:
        self.notifications += 1
        return self.notify_result


def _catalog() -> AssignablePermissionCatalog:
    return AssignablePermissionCatalogFake(
        connector_tools={
            "github": ("list_repositories", "create_issue"),
            "slack": ("read_channel_messages",),
        }
    )


def _management(
    store: GroupPermissionStore, notify_result: bool = True
) -> AdminGroupPermissionManagement:
    return GroupPermissionManagementService(
        store=store,
        catalog=_catalog(),
        notifier=RecordingPermissionChangeNotifier(notify_result=notify_result),
    )


@pytest_asyncio.fixture(params=["in_memory", "sqlite"])
async def store(request: pytest.FixtureRequest, tmp_path: Path) -> GroupPermissionStore:
    if request.param == "sqlite":
        database = (await prepared_sqlite_runtime(tmp_path / "permissions.sqlite3")).database
        return await create_group_permission_store(database)
    database = (await prepared_inmemory_runtime()).database
    return GroupPermissionStoreService(
        database, GROUP_TABLE, CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE
    )


@pytest.mark.asyncio
async def test_admin_grants_group_access_to_connector_tool(store: GroupPermissionStore) -> None:
    management = _management(store)
    tool = ConnectorToolRef("github", "list_repositories")
    result = await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering", connector_ids=(), capabilities=(tool.as_capability(),)
        )
    )
    assert result.status == "applied"
    assert tool in (await management.list_group_permissions("engineering")).tools


@pytest.mark.asyncio
async def test_admin_lists_current_permissions_for_group(store: GroupPermissionStore) -> None:
    management = _management(store)
    tool = ConnectorToolRef("slack", "read_channel_messages")
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="support", connector_ids=("slack",), capabilities=(tool.as_capability(),)
        )
    )
    permissions = await management.list_group_permissions("support")
    assert permissions == GroupPermissionSet(
        group_id="support", connector_ids=("slack",), capabilities=(tool.as_capability(),)
    )


@pytest.mark.asyncio
async def test_admin_lists_group_identifiers_without_permission_details(
    store: GroupPermissionStore,
) -> None:
    management = _management(store)
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(group_id="z-Team", connector_ids=("github",), capabilities=())
    )
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="A-team",
            connector_ids=(),
            capabilities=(ConnectorToolRef("slack", "read_channel_messages").as_capability(),),
        )
    )
    await management.register_permission_group("empty")
    assert await management.list_group_identifiers() == (
        GroupPermissionSummary(group_id="A-team"),
        GroupPermissionSummary(group_id="empty"),
        GroupPermissionSummary(group_id="z-Team"),
    )


@pytest.mark.asyncio
async def test_admin_saves_all_permissions_for_group(store: GroupPermissionStore) -> None:
    management = _management(store)
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering",
            connector_ids=(),
            capabilities=(
                ConnectorToolRef("github", "list_repositories").as_capability(),
                ConnectorToolRef("slack", "read_channel_messages").as_capability(),
            ),
        )
    )
    result = await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering",
            connector_ids=(),
            capabilities=(ConnectorToolRef("github", "create_issue").as_capability(),),
        )
    )
    assert result.status == "applied"
    assert await management.list_group_permissions("engineering") == GroupPermissionSet(
        group_id="engineering",
        connector_ids=(),
        capabilities=(ConnectorToolRef("github", "create_issue").as_capability(),),
    )


@pytest.mark.asyncio
async def test_partial_update_changes_only_named_permissions(store: GroupPermissionStore) -> None:
    management = _management(store)
    omitted_tool = ConnectorToolRef("github", "list_repositories")
    enabled_tool = ConnectorToolRef("github", "create_issue")
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering",
            connector_ids=("slack",),
            capabilities=(omitted_tool.as_capability(),),
        )
    )
    result = await management.update_group_permissions(
        UpdateGroupPermissionsRequest(
            group_id="engineering",
            connectors=(ConnectorPermissionUpdate("slack", "disabled"),),
            capabilities=(
                CapabilityPermissionUpdate(enabled_tool.as_capability(), "enabled"),
            ),
        )
    )
    assert result.status == "applied"
    assert await management.list_group_permissions("engineering") == GroupPermissionSet(
        group_id="engineering",
        connector_ids=(),
        capabilities=(enabled_tool.as_capability(), omitted_tool.as_capability()),
    )


@pytest.mark.asyncio
async def test_partial_update_with_unknown_target_does_not_mutate_valid_target(
    store: GroupPermissionStore,
) -> None:
    management = _management(store)
    result = await management.update_group_permissions(
        UpdateGroupPermissionsRequest(
            group_id="engineering",
            connectors=(ConnectorPermissionUpdate("github", "enabled"),),
            capabilities=(
                CapabilityPermissionUpdate(
                    ConnectorToolRef("github", "missing_operation").as_capability(),
                    "enabled",
                ),
            ),
        )
    )
    assert result.status == "rejected"
    assert await management.list_group_permissions("engineering") == GroupPermissionSet(
        group_id="engineering", connector_ids=(), capabilities=()
    )


@pytest.mark.asyncio
async def test_partial_update_allows_disabling_unknown_capability(
    store: GroupPermissionStore,
) -> None:
    management = _management(store)
    stale = ConnectorCapabilityRef("github", "tool", "retired_operation")
    await store.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering",
            connector_ids=(),
            capabilities=(ConnectorToolRef("github", "create_issue").as_capability(), stale),
        )
    )
    result = await management.update_group_permissions(
        UpdateGroupPermissionsRequest(
            group_id="engineering",
            connectors=(),
            capabilities=(CapabilityPermissionUpdate(stale, "disabled"),),
        )
    )
    assert result.status == "applied"
    assert await management.list_group_permissions("engineering") == GroupPermissionSet(
        group_id="engineering",
        connector_ids=(),
        capabilities=(ConnectorToolRef("github", "create_issue").as_capability(),),
    )


@pytest.mark.asyncio
async def test_repeated_partial_update_is_idempotent(store: GroupPermissionStore) -> None:
    management = _management(store)
    request = UpdateGroupPermissionsRequest(
        group_id="engineering",
        connectors=(ConnectorPermissionUpdate("github", "enabled"),),
        capabilities=(),
    )
    await management.update_group_permissions(request)
    await management.update_group_permissions(request)
    assert await management.list_group_permissions("engineering") == GroupPermissionSet(
        group_id="engineering", connector_ids=("github",), capabilities=()
    )


@pytest.mark.asyncio
async def test_admin_cannot_grant_permission_for_unknown_connector_tool(
    store: GroupPermissionStore,
) -> None:
    management = _management(store)
    result = await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering",
            connector_ids=(),
            capabilities=(ConnectorToolRef("github", "delete_repository").as_capability(),),
        )
    )
    assert result.status == "rejected"
    assert (
        ConnectorToolRef("github", "delete_repository")
        not in (await management.list_group_permissions("engineering")).tools
    )


@pytest.mark.asyncio
async def test_admin_cannot_grant_permission_for_unknown_connector(
    store: GroupPermissionStore,
) -> None:
    management = _management(store)
    result = await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering", connector_ids=("gitlab",), capabilities=()
        )
    )
    assert result.status == "rejected"
    assert (await management.list_group_permissions("engineering")).connector_ids == ()


@pytest.mark.asyncio
async def test_admin_revokes_previously_granted_tool(store: GroupPermissionStore) -> None:
    management = _management(store)
    tool = ConnectorToolRef("github", "create_issue")
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering", connector_ids=(), capabilities=(tool.as_capability(),)
        )
    )
    result = await management.update_group_permissions(
        UpdateGroupPermissionsRequest(
            group_id="engineering",
            connectors=(),
            capabilities=(CapabilityPermissionUpdate(tool.as_capability(), "disabled"),),
        )
    )
    assert result.status == "applied"
    assert tool not in (await management.list_group_permissions("engineering")).tools


@pytest.mark.asyncio
async def test_applied_change_reports_clients_notified_from_notifier(
    store: GroupPermissionStore,
) -> None:
    notifier = RecordingPermissionChangeNotifier(notify_result=True)
    management = GroupPermissionManagementService(
        store=store, catalog=_catalog(), notifier=notifier
    )
    tool = ConnectorToolRef("github", "create_issue")
    await management.save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering", connector_ids=(), capabilities=(tool.as_capability(),)
        )
    )
    result = await management.update_group_permissions(
        UpdateGroupPermissionsRequest(
            group_id="engineering",
            connectors=(),
            capabilities=(CapabilityPermissionUpdate(tool.as_capability(), "disabled"),),
        )
    )
    assert result.clients_notified is True
    assert notifier.notifications == 2


@pytest.mark.asyncio
async def test_permissions_persist_across_store_recreation(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "permissions.sqlite3"
    tool = ConnectorToolRef("github", "list_repositories")
    database = (await prepared_sqlite_runtime(sqlite_path)).database
    store = await create_group_permission_store(database)
    await _management(store).save_group_permissions(
        SaveGroupPermissionsRequest(
            group_id="engineering", connector_ids=(), capabilities=(tool.as_capability(),)
        )
    )
    reopened_store = await create_group_permission_store(database)
    reopened = _management(reopened_store)
    assert tool in (await reopened.list_group_permissions("engineering")).tools
