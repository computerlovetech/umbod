import asyncio

import pytest

from tests.umbod.core.persistence.contract_support import (
    GeneratedRow,
    SampleKey,
    generated_table,
    row,
    serialized_claim_observations,
    table,
)
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


@pytest.mark.asyncio
async def test_serialized_claim_reads_previous_claimants_committed_state(database: Database) -> None:
    assert await serialized_claim_observations(database, database) == ("available", "claimed")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", tuple(TransactionMode))
@pytest.mark.parametrize("interruption", ("exception", "cancellation"))
async def test_mixed_mutations_across_tables_roll_back_together(
    database: Database, mode: TransactionMode, interruption: str,
) -> None:
    primary, _, record, _ = table("primary_records")
    secondary, _, secondary_record, _ = table("secondary_records")
    generated, sequence = generated_table("generated_records")
    await database.ensure_schema((primary, secondary, generated))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(primary, InsertCommand(row=row("updated", "before")))
        await session.insert(primary, InsertCommand(row=row("deleted", "preserved")))
        await session.insert(secondary, InsertCommand(row=row("retained", "preserved")))
        committed_key = await session.insert_generated_integer_key(
            generated,
            GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="committed"), sequence),
        )
    mutations_ready = asyncio.Event()
    release = asyncio.Event()

    async def interrupted_transaction() -> None:
        async with database.session(mode=mode) as session:
            await session.upsert(
                primary,
                UpsertCommand(
                    key=SampleKey(owner_id="owner", record_id="updated"),
                    row=row("updated", "uncommitted"),
                ),
            )
            await session.delete(primary, DeleteQuery(Equals(record, "deleted")))
            await session.insert(secondary, InsertCommand(row=row("inserted", "uncommitted")))
            await session.insert_generated_integer_key(
                generated,
                GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="uncommitted"), sequence),
            )
            mutations_ready.set()
            await release.wait()
            raise RuntimeError("interrupted after mixed mutations")

    task = asyncio.create_task(interrupted_transaction())
    try:
        await asyncio.wait_for(mutations_ready.wait(), timeout=10)
        if interruption == "cancellation":
            task.cancel()
        else:
            release.set()
        expected_error = asyncio.CancelledError if interruption == "cancellation" else RuntimeError
        with pytest.raises(expected_error):
            await asyncio.wait_for(task, timeout=10)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async with database.read_session() as session:
        assert await session.find_many(primary, Query(NoFilter(), AllFields(), OrderBy((record,)))) == (
            row("deleted", "preserved"), row("updated", "before"),
        )
        assert await session.find_many(secondary, Query(NoFilter(), AllFields(), OrderBy((secondary_record,)))) == (
            row("retained", "preserved"),
        )
        assert await session.find_many(generated, Query(NoFilter(), AllFields(), OrderBy((sequence,)))) == (
            GeneratedRow(sequence=committed_key, payload="committed"),
        )

    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        next_key = await session.insert_generated_integer_key(
            generated,
            GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="subsequent"), sequence),
        )
    assert next_key > committed_key
    async with database.read_session() as session:
        assert await session.find_many(generated, Query(NoFilter(), AllFields(), OrderBy((sequence,)))) == (
            GeneratedRow(sequence=committed_key, payload="committed"),
            GeneratedRow(sequence=next_key, payload="subsequent"),
        )
