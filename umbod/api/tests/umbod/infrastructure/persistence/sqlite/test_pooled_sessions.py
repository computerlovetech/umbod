import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from tests.umbod.core.persistence.contract_support import row, table
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from umbod.infrastructure.connections import ConnectionPool
from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[SQLiteDatabase]:
    path = str(tmp_path / "pooled.sqlite")
    connections = ConnectionPool(SQLiteConnectionDriver(path, create_parent_dirs=False), size=1)
    database = SQLiteDatabase(connections)
    try:
        await connections.initialize()
        yield database
    finally:
        await connections.close()


@pytest.mark.asyncio
async def test_read_only_connection_can_be_reused_for_a_committed_write(database: SQLiteDatabase) -> None:
    records, _, _, _ = table("pooled_records")
    await database.ensure_schema((records,))
    query = Query(NoFilter(), AllFields(), Unordered())
    async with database.read_session() as reader:
        assert await reader.find_many(records, query) == ()
    expected = row("committed", "value")
    async with database.session(mode=TransactionMode.READ_WRITE) as writer:
        await writer.insert(records, InsertCommand(row=expected))
    async with database.read_session() as reader:
        assert await reader.find_many(records, query) == (expected,)


@pytest.mark.asyncio
async def test_cancelled_write_is_rolled_back_before_connection_reuse(database: SQLiteDatabase) -> None:
    records, _, _, _ = table("pooled_records")
    await database.ensure_schema((records,))
    inserted = asyncio.Event()

    async def write_until_cancelled() -> None:
        async with database.session(mode=TransactionMode.READ_WRITE) as writer:
            await writer.insert(records, InsertCommand(row=row("cancelled", "value")))
            inserted.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(write_until_cancelled())
    try:
        await asyncio.wait_for(inserted.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        async with database.read_session() as reader:
            assert await reader.find_many(records, Query(NoFilter(), AllFields(), Unordered())) == ()
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as writer:
            assert await writer.insert(records, InsertCommand(row=row("next", "value")))
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
