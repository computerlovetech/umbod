import asyncio

import pytest

from umbod.core.persistence import (
    AllFields,
    Database,
    InsertCommand,
    NoFilter,
    OrderBy,
    Query,
    TransactionMode,
    UpsertCommand,
)
from tests.umbod.core.persistence.contract_support import SampleKey, row, table


@pytest.mark.asyncio
async def test_read_snapshot_survives_interleaved_committed_writer_without_lost_updates(
    database: Database,
) -> None:
    contract_table, _, record, _ = table()
    await database.ensure_schema((contract_table,))
    query = Query(NoFilter(), AllFields(), OrderBy((record,)))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row("record", "before")))

    async def write() -> None:
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(
                contract_table,
                UpsertCommand(key=SampleKey(owner_id="owner", record_id="record"), row=row("record", "after")),
            )
            await session.insert(contract_table, InsertCommand(row=row("second", "new")))

    async with database.read_session() as reader:
        assert await reader.find_one(contract_table, query) == row("record", "before")
        await asyncio.wait_for(write(), timeout=2)
        assert await reader.find_many(contract_table, query) == (row("record", "before"),)
        assert await reader.find_one(contract_table, query) == row("record", "before")
    async with database.read_session() as reader:
        assert await reader.find_many(contract_table, query) == (
            row("record", "after"), row("second", "new"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ("insert", "insert_generated_integer_key", "upsert", "delete", "ensure_schema"))
async def test_read_facade_exposes_no_mutations(database: Database, name: str) -> None:
    async with database.read_session() as reader:
        assert not hasattr(reader, name)


@pytest.mark.asyncio
async def test_exception_in_read_session_releases_resources(database: Database) -> None:
    contract_table, _, record, _ = table()
    await database.ensure_schema((contract_table,))
    query = Query(NoFilter(), AllFields(), OrderBy((record,)))
    with pytest.raises(RuntimeError, match="read failed"):
        async with database.read_session() as reader:
            assert await reader.find_many(contract_table, query) == ()
            raise RuntimeError("read failed")
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as writer:
        await writer.insert(contract_table, InsertCommand(row=row("retained", "value")))
    async with database.read_session() as reader:
        assert await reader.find_one(contract_table, query) == row("retained", "value")


@pytest.mark.asyncio
async def test_cancellation_in_read_session_releases_resources(database: Database) -> None:
    contract_table, _, record, _ = table()
    await database.ensure_schema((contract_table,))
    query = Query(NoFilter(), AllFields(), OrderBy((record,)))
    reading = asyncio.Event()

    async def read_until_cancelled() -> None:
        async with database.read_session() as reader:
            await reader.find_many(contract_table, query)
            reading.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(read_until_cancelled())
    try:
        await asyncio.wait_for(reading.wait(), timeout=2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as writer:
        await writer.insert(contract_table, InsertCommand(row=row("retained", "value")))
    async with database.read_session() as reader:
        assert await reader.find_many(contract_table, query) == (row("retained", "value"),)
