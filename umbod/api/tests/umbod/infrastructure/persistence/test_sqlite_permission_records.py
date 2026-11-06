import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from umbod.core.groups.stores.schema import GROUP_ID, GROUP_TABLE, PermissionGroupRecord
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_CONNECTOR_ID,
    CAPABILITY_PERMISSION_GROUP_ID,
    CAPABILITY_PERMISSION_KEY,
    CAPABILITY_PERMISSION_KIND,
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_GROUP_ID,
    CONNECTOR_PERMISSION_TABLE,
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Equals,
    InsertCommand,
    NoFilter,
    OrderBy,
    Query,
    TransactionMode,
    Unordered,
)


@pytest.mark.asyncio
async def test_sqlite_group_and_permission_records_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "permissions.sqlite3"
    groups = (
        PermissionGroupRecord(group_id="empty-group", label="Empty ☃", description="", revision=1),
        PermissionGroupRecord(
            group_id="engineering", label="Engineering 雪",
            description='Team "description"\n\\path', revision=2,
        ),
        PermissionGroupRecord(group_id="other-team", label="Other", description="Neighbor", revision=3),
    )
    permissions = tuple(
        GroupCapabilityPermissionRecord(
            group_id=group_id, connector_id=connector_id,
            capability_kind=capability_kind, capability_key=capability_key,
        )
        for group_id, connector_id, capability_kind, capability_key in (
            ("engineering", "test", "tool", "echo"),
            ("engineering", "other-connector", "tool", "echo"),
            ("other-team", "test", "tool", "echo"),
            ("engineering", "test", "resource", "echo"),
            ("engineering", "test", "tool", "other-operation"),
        )
    )
    neighbor_connector = GroupConnectorPermissionRecord(group_id="other-team", connector_id="test")
    writer = create_sqlite_runtime(path)
    try:
        await writer.readiness.ensure_ready()
        async with writer.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for group in groups:
                assert await session.insert(GROUP_TABLE, InsertCommand(row=group))
            for permission in permissions:
                assert await session.insert(CAPABILITY_PERMISSION_TABLE, InsertCommand(row=permission))
            assert await session.insert(CONNECTOR_PERMISSION_TABLE, InsertCommand(row=neighbor_connector))
            assert not await session.insert(GROUP_TABLE, InsertCommand(row=groups[1]))
            assert not await session.insert(CAPABILITY_PERMISSION_TABLE, InsertCommand(row=permissions[0]))
            assert not await session.insert(CONNECTOR_PERMISSION_TABLE, InsertCommand(row=neighbor_connector))
    finally:
        await writer.shutdown()

    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        async with reader.database.read_session() as session:
            restored_groups = await session.find_many(
                GROUP_TABLE, Query(NoFilter(), AllFields(), OrderBy((GROUP_ID,))),
            )
            restored_permissions = await session.find_many(
                CAPABILITY_PERMISSION_TABLE, Query(NoFilter(), AllFields(), Unordered()),
            )
            engineering_connectors = await session.find_many(
                CONNECTOR_PERMISSION_TABLE,
                Query(Equals(CONNECTOR_PERMISSION_GROUP_ID, "engineering"), AllFields(), Unordered()),
            )
            neighbor_connectors = await session.find_many(
                CONNECTOR_PERMISSION_TABLE,
                Query(Equals(CONNECTOR_PERMISSION_GROUP_ID, "other-team"), AllFields(), Unordered()),
            )
            assert restored_groups == groups
            assert set(restored_permissions) == set(permissions)
            assert engineering_connectors == ()
            assert neighbor_connectors == (neighbor_connector,)
            for permission in permissions:
                assert await session.find_many(
                    CAPABILITY_PERMISSION_TABLE,
                    Query(
                        AllOf((
                            Equals(CAPABILITY_PERMISSION_GROUP_ID, permission.group_id),
                            Equals(CAPABILITY_PERMISSION_CONNECTOR_ID, permission.connector_id),
                            Equals(CAPABILITY_PERMISSION_KIND, permission.capability_kind),
                            Equals(CAPABILITY_PERMISSION_KEY, permission.capability_key),
                        )),
                        AllFields(), Unordered(),
                    ),
                ) == (permission,)
    finally:
        await reader.shutdown()

    with closing(sqlite3.connect(path)) as connection, connection:
        raw_groups = connection.execute(
            "SELECT group_id, label, description, revision, typeof(revision) "
            "FROM mcp_permission_groups ORDER BY group_id"
        ).fetchall()
        raw_permissions = connection.execute(
            "SELECT group_id, connector_id, capability_kind, capability_key, "
            "typeof(group_id), typeof(connector_id), typeof(capability_kind), typeof(capability_key) "
            "FROM mcp_group_capability_permissions"
        ).fetchall()
        permission_columns = connection.execute(
            "PRAGMA table_info(mcp_group_capability_permissions)"
        ).fetchall()
        connector_columns = connection.execute(
            "PRAGMA table_info(mcp_group_connector_permissions)"
        ).fetchall()
    assert raw_groups == [
        (group.group_id, group.label, group.description, group.revision, "integer")
        for group in groups
    ]
    assert set(raw_permissions) == {
        (permission.group_id, permission.connector_id, permission.capability_kind,
         permission.capability_key, "text", "text", "text", "text")
        for permission in permissions
    }
    assert {column[1]: column[5] for column in permission_columns if column[5]} == {
        "group_id": 1, "connector_id": 2, "capability_kind": 3, "capability_key": 4,
    }
    assert {column[1]: column[5] for column in connector_columns if column[5]} == {
        "group_id": 1, "connector_id": 2,
    }
