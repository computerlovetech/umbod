from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.messaging import reject_database_event_appends
from umbod.core.persistence import Database
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.permissions import CapabilityPermissionUpdate, ConnectorCapabilityRef, ConnectorPermissionUpdate, GroupPermissionStore, SaveGroupPermissionsRequest, UpdateGroupPermissionsRequest
from umbod.core.permissions.factories import create_group_permission_store


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("update", "save"))
@pytest.mark.parametrize("action", ("grant", "revoke"))
async def test_permission_event_append_failure_rolls_back_grants(
    database: Database, monkeypatch: pytest.MonkeyPatch, operation: str, action: str,
) -> None:
    store: GroupPermissionStore = await create_group_permission_store(database)
    capability = ConnectorCapabilityRef(connector_id="test", capability_kind="tool", capability_key="echo")
    if action == "revoke":
        await store.save_group_permissions(SaveGroupPermissionsRequest(
            group_id="readers", connector_ids=("test",), capabilities=(capability,),
        ))
    previous = await store.list_group_permissions("readers")
    events = DatabaseEventStream(database)
    previous_events = await events.list_after(0, 100)
    reject_database_event_appends(database, monkeypatch)
    with pytest.raises(RuntimeError, match="event append failed"):
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
async def test_permission_mutations_publish_once_and_noop_updates_publish_nothing(database: Database) -> None:
    store: GroupPermissionStore = await create_group_permission_store(database)
    command = UpdateGroupPermissionsRequest(
        group_id="readers",
        connectors=(ConnectorPermissionUpdate(connector_id="test", permission_status="enabled"),),
        capabilities=(),
    )
    await store.update_group_permissions(command)
    await store.update_group_permissions(command)
    events = await DatabaseEventStream(database).list_after(0, 100)
    assert len(events) == 1
    assert events[0].event.event_type == "mcp.group_permission.changed"
    assert events[0].event.metadata["action"] == "grant"
