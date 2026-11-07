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


from tests.support.persistence_contracts import (
    GeneratedKey,
    GeneratedRow,
    generated_table,
    non_reusing_generated_table,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", tuple(TransactionMode))
@pytest.mark.parametrize("delete_all", (False, True), ids=("highest", "all"))
async def test_generated_keys_remain_above_committed_history_after_deletion(
    database: Database, mode: TransactionMode, delete_all: bool
) -> None:
    table, sequence = non_reusing_generated_table()
    await database.ensure_schema((table,))
    async with database.session(mode=mode) as session:
        first = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="first"), sequence
            ),
        )
        highest = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="highest"), sequence
            ),
        )
    async with database.session(mode=mode) as session:
        deleted = await session.delete(
            table, DeleteQuery(NoFilter() if delete_all else Equals(sequence, highest))
        )
    assert highest > first
    assert deleted == (2 if delete_all else 1)
    async with database.session(mode=mode) as session:
        allocated = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="next"), sequence
            ),
        )
    assert allocated > highest
    async with database.read_session() as session:
        rows = await session.find_many(
            table, Query(NoFilter(), AllFields(), OrderBy((sequence,)))
        )
    retained = () if delete_all else (GeneratedRow(sequence=first, payload="first"),)
    assert tuple(rows) == (*retained, GeneratedRow(sequence=allocated, payload="next"))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", tuple(TransactionMode))
@pytest.mark.parametrize("operation", ("insert", "upsert"))
async def test_explicit_keys_advance_history_even_after_deletion(
    database: Database, mode: TransactionMode, operation: str
) -> None:
    table, sequence = non_reusing_generated_table()
    await database.ensure_schema((table,))
    high = 1000
    async with database.session(mode=mode) as session:
        row = GeneratedRow(sequence=high, payload="explicit")
        if operation == "insert":
            assert await session.insert(table, InsertCommand(row=row)) is True
            assert await session.insert(table, InsertCommand(row=row)) is False
        else:
            await session.upsert(
                table, UpsertCommand(key=GeneratedKey(sequence=high), row=row)
            )
    async with database.session(mode=mode) as session:
        assert await session.delete(table, DeleteQuery(NoFilter())) == 1
    async with database.session(mode=mode) as session:
        allocated = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="next"), sequence
            ),
        )
    assert allocated > high
    async with database.read_session() as session:
        rows = await session.find_many(
            table, Query(NoFilter(), AllFields(), OrderBy((sequence,)))
        )
    assert tuple(rows) == (GeneratedRow(sequence=allocated, payload="next"),)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", tuple(TransactionMode))
async def test_rollback_removes_aborted_rows_without_losing_committed_history(
    database: Database, mode: TransactionMode
) -> None:
    table, sequence = non_reusing_generated_table()
    await database.ensure_schema((table,))
    async with database.session(mode=mode) as session:
        committed = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="committed"), sequence
            ),
        )
    with pytest.raises(RuntimeError, match="rollback"):
        async with database.session(mode=mode) as session:
            await session.insert_generated_integer_key(
                table,
                GeneratedIntegerKeyInsertCommand(
                    GeneratedRow(sequence=0, payload="aborted"), sequence
                ),
            )
            await session.upsert(
                table,
                UpsertCommand(
                    key=GeneratedKey(sequence=1000),
                    row=GeneratedRow(sequence=1000, payload="aborted explicit"),
                ),
            )
            raise RuntimeError("rollback")
    async with database.read_session() as session:
        rows = await session.find_many(
            table, Query(NoFilter(), AllFields(), OrderBy((sequence,)))
        )
    assert rows == (GeneratedRow(sequence=committed, payload="committed"),)
    async with database.session(mode=mode) as session:
        assert await session.delete(table, DeleteQuery(NoFilter())) == 1
    async with database.session(mode=mode) as session:
        allocated = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="next"), sequence
            ),
        )
    assert allocated > committed


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", tuple(TransactionMode))
async def test_non_reusing_key_history_is_independent_per_table(
    database: Database, mode: TransactionMode
) -> None:
    first, first_sequence = non_reusing_generated_table("first_non_reusing_samples")
    second, second_sequence = non_reusing_generated_table("second_non_reusing_samples")
    await database.ensure_schema((first, second))
    async with database.session(mode=mode) as session:
        assert (
            await session.insert(
                first, InsertCommand(row=GeneratedRow(sequence=1000, payload="high"))
            )
            is True
        )
    async with database.session(mode=mode) as session:
        assert await session.delete(first, DeleteQuery(NoFilter())) == 1
    async with database.session(mode=mode) as session:
        independent = await session.insert_generated_integer_key(
            second,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="independent"), second_sequence
            ),
        )
        continued = await session.insert_generated_integer_key(
            first,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="continued"), first_sequence
            ),
        )
    assert independent == 1
    assert continued > 1000


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", tuple(TransactionMode))
@pytest.mark.parametrize("operation", ("insert", "upsert"))
async def test_registered_non_reuse_policy_covers_ordinary_descriptors(
    database: Database, mode: TransactionMode, operation: str
) -> None:
    opted_in, sequence = non_reusing_generated_table("registered_samples")
    ordinary, _ = generated_table("registered_samples")
    await database.ensure_schema((opted_in,))
    await database.ensure_schema((ordinary,))
    async with database.session(mode=mode) as session:
        explicit = GeneratedRow(sequence=1000, payload="explicit")
        if operation == "insert":
            assert await session.insert(ordinary, InsertCommand(row=explicit)) is True
        else:
            await session.upsert(
                ordinary,
                UpsertCommand(key=GeneratedKey(sequence=1000), row=explicit),
            )
    async with database.session(mode=mode) as session:
        assert await session.delete(ordinary, DeleteQuery(NoFilter())) == 1
    async with database.session(mode=mode) as session:
        allocated = await session.insert_generated_integer_key(
            opted_in,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="next"), sequence
            ),
        )
    assert allocated > 1000
    async with database.read_session() as session:
        rows = await session.find_many(
            opted_in, Query(NoFilter(), AllFields(), OrderBy((sequence,)))
        )
    assert tuple(rows) == (GeneratedRow(sequence=allocated, payload="next"),)


@pytest.mark.asyncio
async def test_existing_ordinary_table_requires_explicit_non_reuse_migration(
    database: Database,
) -> None:
    ordinary, _ = generated_table("existing_samples")
    opted_in, sequence = non_reusing_generated_table("existing_samples")
    await database.ensure_schema((ordinary,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert (
            await session.insert(
                ordinary,
                InsertCommand(row=GeneratedRow(sequence=1000, payload="deleted")),
            )
            is True
        )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.delete(ordinary, DeleteQuery(NoFilter())) == 1
    with pytest.raises(ValueError, match="migration"):
        await database.ensure_schema((opted_in,))
    async with database.read_session() as session:
        rows = await session.find_many(
            ordinary, Query(NoFilter(), AllFields(), OrderBy((sequence,)))
        )
    assert tuple(rows) == ()


@pytest.mark.asyncio
async def test_conflicting_schema_policy_batch_is_atomic(database: Database) -> None:
    ordinary, _ = generated_table("conflicting_samples")
    opted_in, sequence = non_reusing_generated_table("conflicting_samples")
    with pytest.raises(ValueError, match="migration"):
        await database.ensure_schema((ordinary, opted_in))
    await database.ensure_schema((opted_in,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        allocated = await session.insert_generated_integer_key(
            opted_in,
            GeneratedIntegerKeyInsertCommand(
                GeneratedRow(sequence=0, payload="retained"), sequence
            ),
        )
    async with database.read_session() as session:
        rows = await session.find_many(
            opted_in, Query(NoFilter(), AllFields(), OrderBy((sequence,)))
        )
    assert tuple(rows) == (GeneratedRow(sequence=allocated, payload="retained"),)
