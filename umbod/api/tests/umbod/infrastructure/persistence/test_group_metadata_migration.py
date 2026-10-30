from pathlib import Path

import aiosqlite
import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.groups import Group, RegisterGroup, UpdateGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.permissions.factories import create_group_permission_store


@pytest.mark.asyncio
async def test_legacy_sqlite_groups_are_backfilled_and_metadata_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    async with aiosqlite.connect(path) as connection:
        await connection.execute("CREATE TABLE mcp_permission_groups (group_id TEXT PRIMARY KEY NOT NULL)")
        await connection.executemany(
            "INSERT INTO mcp_permission_groups (group_id) VALUES (?)",
            [("provider/team",), ("",), (" " ,), ("x" * 201,)],
        )
        await connection.commit()
    runtime = await prepared_sqlite_runtime(path)
    management = create_group_management(runtime.database)
    try:
        groups = await management.list_groups()
        assert groups == tuple(
            Group(group_id=value, label=value, description="", revision=1)
            for value in ("", " ", "provider/team", "x" * 201)
        )
        updated = await management.update_group_metadata(
            "provider/team", UpdateGroupMetadata(label="Team", description="Edited", expected_revision=1)
        )
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        management = create_group_management(reopened.database)
        await management.register_group(RegisterGroup(group_id="provider/team"))
        assert updated in await management.list_groups()
        store = await create_group_permission_store(reopened.database)
        assert tuple(group.group_id for group in await store.list_group_identifiers()) == ("", " ", "provider/team", "x" * 201)
    finally:
        await reopened.shutdown()
