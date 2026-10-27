import sqlite3
from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.permissions import CapabilityPermissionUpdate, ConnectorCapabilityRef, ConnectorPermissionUpdate, GroupPermissionStore, SaveGroupPermissionsRequest, UpdateGroupPermissionsRequest
from umbod.core.permissions.factories import create_group_permission_store


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("update", "save"))
@pytest.mark.parametrize("action", ("grant", "revoke"))
async def test_permission_event_append_failure_rolls_back_grants(
    tmp_path: Path, operation: str, action: str,
) -> None:
    path = tmp_path / "permissions.sqlite3"
    runtime = await prepared_sqlite_runtime(path)
    store: GroupPermissionStore = await create_group_permission_store(runtime.database)
    capability = ConnectorCapabilityRef(connector_id="test", capability_kind="tool", capability_key="echo")
    if action == "revoke":
        await store.save_group_permissions(SaveGroupPermissionsRequest(
            group_id="readers", connector_ids=("test",), capabilities=(capability,),
        ))
    previous = await store.list_group_permissions("readers")
    events = DatabaseEventStream(runtime.database)
    previous_events = await events.list_after(0, 100)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON messaging_events BEGIN SELECT RAISE(ABORT, 'event append failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        if operation == "update":
            await store.update_group_permissions(UpdateGroupPermissionsRequest(
                group_id="readers",
                connectors=(ConnectorPermissionUpdate(connector_id="test", permission_status="enabled" if action == "grant" else "disabled"),),
                capabilities=(CapabilityPermissionUpdate(capability=capability, permission_status="enabled" if action == "grant" else "disabled"),),
            ))
        else:
            await store.save_group_permissions(SaveGroupPermissionsRequest(
                group_id="readers",
                connector_ids=("test",) if action == "grant" else (),
                capabilities=(capability,) if action == "grant" else (),
            ))
    assert await store.list_group_permissions("readers") == previous
    assert await events.list_after(0, 100) == previous_events


@pytest.mark.asyncio
async def test_permission_mutations_publish_once_and_noop_updates_publish_nothing(tmp_path: Path) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "permissions.sqlite3")
    store: GroupPermissionStore = await create_group_permission_store(runtime.database)
    command = UpdateGroupPermissionsRequest(
        group_id="readers",
        connectors=(ConnectorPermissionUpdate(connector_id="test", permission_status="enabled"),),
        capabilities=(),
    )
    await store.update_group_permissions(command)
    await store.update_group_permissions(command)
    events = await DatabaseEventStream(runtime.database).list_after(0, 100)
    assert len(events) == 1
    assert events[0].event.event_type == "mcp.group_permission.changed"
    assert events[0].event.metadata["action"] == "grant"
