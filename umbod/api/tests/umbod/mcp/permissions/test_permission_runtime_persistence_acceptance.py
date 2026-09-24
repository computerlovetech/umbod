from umbod.core.permissions.factories import create_group_permission_store
from umbod.core.permissions.stores.service import GroupPermissionStoreService
from tests.persistence_runtime import prepared_sqlite_runtime
from pathlib import Path
import pytest
from umbod.core.permissions import AssignablePermissionCatalog, AssignablePermissionTargets, ConnectorToolPermission, ConnectorToolRef, GroupPermissionManagementService, InMemoryGroupConnectorToolPermissions, NoopPermissionChangeNotifier, SaveGroupPermissionsRequest, ToolPermissionUpdate, UpdateGroupPermissionsRequest
from umbod.mcp.live_permission_updates import GroupPermissionStateReloader

class AssignablePermissionCatalogFake:

    async def has_connector(self, connector_id: str) -> bool:
        return connector_id == 'github'

    async def has_capability(self, capability: object) -> bool:
        from umbod.core.permissions import ConnectorCapabilityRef

        if not isinstance(capability, ConnectorCapabilityRef):
            return False
        return capability.connector_id == 'github' and capability.capability_kind == 'tool' and capability.capability_key in {
            'list_repositories',
            'create_issue',
        }

    async def has_tool(self, tool: ConnectorToolRef) -> bool:
        return await self.has_capability(tool.as_capability())

    async def list_assignable_targets(self) -> AssignablePermissionTargets:
        return AssignablePermissionTargets(connectors=(), capabilities=())

def _catalog() -> AssignablePermissionCatalog:
    return AssignablePermissionCatalogFake()

def _management(store: GroupPermissionStoreService) -> GroupPermissionManagementService:
    return GroupPermissionManagementService(store=store, catalog=_catalog(), notifier=NoopPermissionChangeNotifier())

def _new_runtime(store: GroupPermissionStoreService) -> tuple[InMemoryGroupConnectorToolPermissions, GroupPermissionStateReloader]:
    runtime_permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=('groups',))
    reloader = GroupPermissionStateReloader(permission_reader=store, runtime_permissions=runtime_permissions)
    return (runtime_permissions, reloader)

@pytest.mark.asyncio
async def test_persisted_permissions_are_visible_to_runtime_after_restart(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'permissions.sqlite3'
    tool = ConnectorToolRef('github', 'list_repositories')
    database = (await prepared_sqlite_runtime(sqlite_path)).database
    store = await create_group_permission_store(database)
    await _management(store).save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(), capabilities=(tool.as_capability(),)))
    reopened_store = await create_group_permission_store(database)
    (runtime_permissions, reloader) = _new_runtime(reopened_store)
    await reloader.reload_group_permissions()
    assert runtime_permissions.allowed_tools({'groups': ['engineering']}) == {ConnectorToolPermission('github', 'list_repositories')}

@pytest.mark.asyncio
async def test_revoked_permission_is_hidden_from_runtime_after_reload(tmp_path: Path) -> None:
    database = (await prepared_sqlite_runtime(tmp_path / 'permissions.sqlite3')).database
    store = await create_group_permission_store(database)
    management = _management(store)
    tool = ConnectorToolRef('github', 'create_issue')
    await management.save_group_permissions(SaveGroupPermissionsRequest(group_id='engineering', connector_ids=(), capabilities=(tool.as_capability(),)))
    (runtime_permissions, reloader) = _new_runtime(store)
    await reloader.reload_group_permissions()
    await management.update_group_permissions(UpdateGroupPermissionsRequest(group_id='engineering', connectors=(), capabilities=(ToolPermissionUpdate(tool, 'disabled').as_capability_update(),)))
    await reloader.reload_group_permissions()
    assert runtime_permissions.allowed_tools({'groups': ['engineering']}) == set()
