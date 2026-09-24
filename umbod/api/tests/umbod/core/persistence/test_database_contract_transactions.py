import asyncio

import pytest

from umbod.core.persistence import (
    AllFields,
    Database,
    DeleteQuery,
    Equals,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    NoFilter,
    OrderBy,
    Query,
    TransactionMode,
    UpsertCommand,
)
from tests.umbod.core.persistence.contract_support import (
    GeneratedRow,
    SampleKey,
    generated_table,
    row,
    table,
)


@pytest.mark.asyncio
async def test_schema_preparation_is_idempotent_for_multiple_tables(database: Database) -> None:
    first, _, _, _ = table("first_samples")
    second, _, _, _ = table("second_samples")
    await database.ensure_schema((first, second))
    await database.ensure_schema((first, second))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.insert(first, InsertCommand(row=row("first"))) is True
        assert await session.insert(second, InsertCommand(row=row("second"))) is True


@pytest.mark.asyncio
async def test_read_write_session_commits_on_normal_exit(database: Database) -> None:
    contract_table, _, _, _ = table()
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row("committed")))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        stored = await session.find_one(
            contract_table, Query(NoFilter(), AllFields(), OrderBy(contract_table.key_codec.fields))
        )
    assert stored == row("committed")


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(database: Database) -> None:
    contract_table, _, record, _ = table()
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row("record", "before")))
        await session.upsert(
            contract_table,
            UpsertCommand(
                key=SampleKey(owner_id="owner", record_id="record"), row=row("record", "after")
            ),
        )
        stored = await session.find_one(
            contract_table, Query(Equals(record, "record"), AllFields(), OrderBy((record,)))
        )
    assert stored == row("record", "after")


@pytest.mark.asyncio
async def test_upsert_rejects_key_and_row_mismatch(database: Database) -> None:
    contract_table, _, _, _ = table()
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        with pytest.raises(ValueError, match="key"):
            await session.upsert(
                contract_table,
                UpsertCommand(key=SampleKey(owner_id="owner", record_id="key"), row=row("row")),
            )


@pytest.mark.asyncio
async def test_delete_returns_count_and_is_rolled_back_with_transaction(database: Database) -> None:
    contract_table, _, record, _ = table()
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(contract_table, InsertCommand(row=row("first")))
        await session.insert(contract_table, InsertCommand(row=row("second")))
    with pytest.raises(RuntimeError):
        async with database.session(mode=TransactionMode.READ_WRITE) as session:
            assert await session.delete(contract_table, DeleteQuery(Equals(record, "first"))) == 1
            raise RuntimeError("rollback")
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        stored = await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), OrderBy((record,)))
        )
    assert stored == (row("first"), row("second"))


@pytest.mark.asyncio
async def test_generated_keys_are_unique_for_concurrent_serialized_writes(
    database: Database,
) -> None:
    contract_table, sequence = generated_table()
    await database.ensure_schema((contract_table,))

    async def insert(index: int) -> int:
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            return await session.insert_generated_integer_key(
                contract_table,
                GeneratedIntegerKeyInsertCommand(
                    GeneratedRow(sequence=0, payload=str(index)), sequence
                ),
            )

    generated = await asyncio.gather(*(insert(index) for index in range(12)))
    assert sorted(generated) == list(range(1, 13))
