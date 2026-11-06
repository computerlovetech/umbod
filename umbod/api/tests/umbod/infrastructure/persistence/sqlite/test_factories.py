import asyncio
from pathlib import Path

import aiosqlite
import pytest

from tests.umbod.core.persistence.contract_support import row, table
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from umbod.infrastructure.connections import ConnectionPoolUnavailableError
from umbod.infrastructure.persistence.sqlite.factories import create_pooled_sqlite_database, create_unpooled_sqlite_database


@pytest.mark.asyncio
async def test_unpooled_factory_defers_directory_creation_until_connection_acquisition(tmp_path: Path) -> None:
    path = tmp_path / "parent" / "unpooled.sqlite"
    database = create_unpooled_sqlite_database(str(path), create_parent_dirs=True)
    assert not path.parent.exists()
    async with database.schema_connection() as connection:
        assert path.is_file()
        assert connection.row_factory is aiosqlite.Row
        for statement, expected in (("PRAGMA foreign_keys", 1), ("PRAGMA busy_timeout", 5000)):
            async with connection.execute(statement) as cursor:
                assert (await cursor.fetchone())[0] == expected
    with pytest.raises(ValueError, match="no active connection"):
        await connection.execute("SELECT 1")


@pytest.mark.asyncio
async def test_pooled_factory_returns_matching_resources_without_starting_them(tmp_path: Path) -> None:
    path = tmp_path / "parent" / "pooled.sqlite"
    resources = create_pooled_sqlite_database(str(path), create_parent_dirs=True)
    try:
        assert not path.parent.exists()
        await resources.connections.initialize()
        assert path.is_file()
        async with resources.database.schema_connection() as connection:
            async with connection.execute("PRAGMA database_list") as cursor:
                assert (await cursor.fetchone())[2] == str(path)
        await resources.connections.close()
        with pytest.raises(ConnectionPoolUnavailableError):
            async with resources.database.read_session():
                pytest.fail("the adapter must use the closed injected provider")
    finally:
        await resources.connections.close()


@pytest.mark.asyncio
async def test_memory_database_uses_one_connection_and_preserves_state_between_leases() -> None:
    resources = create_pooled_sqlite_database(":memory:", create_parent_dirs=False)
    records, _, _, _ = table("memory_records")
    started = asyncio.Event()

    async def read_records() -> int:
        started.set()
        async with resources.database.read_session() as reader:
            return len(await reader.find_many(records, Query(NoFilter(), AllFields(), Unordered())))

    try:
        await resources.connections.initialize()
        await resources.database.ensure_schema((records,))
        async with resources.database.session(mode=TransactionMode.READ_WRITE) as writer:
            await writer.insert(records, InsertCommand(row=row("memory", "value")))
        async with resources.connections.get_connection():
            reading = asyncio.create_task(read_records())
            try:
                await asyncio.wait_for(started.wait(), 2)
                for _ in range(3):
                    await asyncio.sleep(0)
                assert not reading.done()
            except BaseException:
                reading.cancel()
                await asyncio.gather(reading, return_exceptions=True)
                raise
        assert await asyncio.wait_for(reading, 2) == 1
    finally:
        await resources.connections.close()
