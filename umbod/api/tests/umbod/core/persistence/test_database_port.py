import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import cast

import pytest

from umbod.core.persistence import (
    AllFields,
    AllOf,
    AnyOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Field,
    Fields,
    GeneratedIntegerKeyInsertCommand,
    GreaterThan,
    InsertCommand,
    NoFilter,
    Not,
    OneOf,
    OrderBy,
    Query,
    Table,
    TableIdentity,
    TextCodec,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from tests.umbod.core.persistence.contract_support import (
    CanonicalRow,
    GeneratedRow,
    PayloadResult,
    RecordResult,
    SampleDocument,
    SampleKey,
    SampleRow,
    canonical_table,
    generated_table,
    row as make_row,
    table as make_table,
)


@asynccontextmanager
async def database_session(
    database: Database, contract_table: Table[SampleRow, SampleKey]
) -> AsyncIterator[DatabaseSession]:
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as database_session:
        yield database_session


@pytest.mark.asyncio
async def test_typed_full_and_projected_reads_order_by_excluded_field(
    database: Database,
) -> None:
    table, owner, record, payload = make_table()
    async with database_session(database, table) as session:
        await session.insert(table, InsertCommand(row=make_row("b")))
        await session.insert(table, InsertCommand(row=make_row("a")))
        full = await session.find_one(table, Query(Equals(record, "a"), AllFields(), Unordered()))
        projected = await session.find_many(
            table,
            Query(
                Equals(owner, "owner"),
                Fields(PayloadResult, cast(tuple[Field[SampleRow, object], ...], (payload,))),
                OrderBy(cast(tuple[Field[SampleRow, object], ...], (record,))),
            ),
        )
    assert full == make_row("a")
    assert projected == (PayloadResult(payload="same"), PayloadResult(payload="same"))


@pytest.mark.parametrize(
    ("predicate_factory", "expected"),
    [
        (lambda record: NoFilter(), ("a", "b")),
        (lambda record: OneOf(record, ()), ()),
        (lambda record: Not(OneOf(record, ())), ("a", "b")),
        (lambda record: AllOf(()), ("a", "b")),
        (lambda record: AnyOf(()), ()),
        (lambda record: OneOf(record, ("b",)), ("b",)),
    ],
)
@pytest.mark.asyncio
async def test_typed_predicate_contract(
    database: Database,
    predicate_factory: Callable[[Field[SampleRow, str]], object],
    expected: tuple[str, ...],
) -> None:
    table, _, record, _ = make_table()
    async with database_session(database, table) as session:
        await session.insert(table, InsertCommand(row=make_row("b")))
        await session.insert(table, InsertCommand(row=make_row("a")))
        rows = await session.find_many(
            table,
            Query(
                cast(object, predicate_factory(record)),
                Fields(RecordResult, cast(tuple[Field[SampleRow, object], ...], (record,))),
                OrderBy(cast(tuple[Field[SampleRow, object], ...], (record,))),
            ),
        )
    assert tuple(row.record_id for row in rows) == expected


@pytest.mark.asyncio
async def test_greater_than_filters_then_orders_before_limit(database: Database) -> None:
    table, _, record, _ = make_table()
    async with database_session(database, table) as session:
        for record_id in ("d", "a", "c", "b"):
            await session.insert(table, InsertCommand(row=make_row(record_id)))
        rows = await session.find_many(
            table,
            Query(GreaterThan(record, "a"), AllFields(), OrderBy((record,)), limit=2),
        )

    assert tuple(row.record_id for row in rows) == ("b", "c")


@pytest.mark.asyncio
async def test_zero_limit_returns_no_result_from_find_one_and_find_many(
    database: Database,
) -> None:
    table, _, _, _ = make_table()
    async with database_session(database, table) as session:
        await session.insert(table, InsertCommand(row=make_row("a")))
        query = Query(NoFilter(), AllFields(), Unordered(), limit=0)
        one = await session.find_one(table, query)
        many = await session.find_many(table, query)

    assert one is None
    assert many == ()


@pytest.mark.parametrize("limit", [True, False, 1.5, "1"])
def test_query_rejects_invalid_limit_types(limit: object) -> None:
    with pytest.raises(TypeError, match="limit must be an integer"):
        Query(NoFilter(), AllFields(), Unordered(), limit=cast(int, limit))


@pytest.mark.asyncio
async def test_generated_integer_insert_assigns_monotonic_keys(database: Database) -> None:
    table, sequence = generated_table()
    await database.ensure_schema((table,))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        first = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="first"), sequence),
        )
        second = await session.insert_generated_integer_key(
            table,
            GeneratedIntegerKeyInsertCommand(GeneratedRow(sequence=0, payload="second"), sequence),
        )
        rows = await session.find_many(table, Query(NoFilter(), AllFields(), OrderBy((sequence,))))

    assert (first, second) == (1, 2)
    assert tuple(row.sequence for row in rows) == (1, 2)


@pytest.mark.asyncio
async def test_typed_rejects_wrong_table_field_and_wrong_runtime_value(
    database: Database,
) -> None:
    table, _, _, _ = make_table()
    _, foreign_owner, _, _ = make_table("other_samples")
    async with database_session(database, table) as session:
        with pytest.raises(ValueError, match="does not belong"):
            await session.find_many(
                table, Query(Equals(foreign_owner, "x"), AllFields(), Unordered())
            )
        with pytest.raises(TypeError, match="expected str"):
            await session.find_many(
                table,
                Query(
                    Equals(foreign_owner.__class__(table.identity, "owner_id", TextCodec()), 3),
                    AllFields(),
                    Unordered(),
                ),
            )


@pytest.mark.asyncio
async def test_typed_composite_insert_upsert_delete_and_duplicate(
    database: Database,
) -> None:
    table, owner, record, _ = make_table()
    async with database_session(database, table) as session:
        assert await session.insert(table, InsertCommand(row=make_row("a", "first"))) is True
        assert await session.insert(table, InsertCommand(row=make_row("a", "duplicate"))) is False
        await session.upsert(
            table,
            UpsertCommand(
                key=SampleKey(owner_id="owner", record_id="a"),
                row=make_row("a", "updated"),
            ),
        )
        deleted = await session.delete(
            table, DeleteQuery(AllOf((Equals(owner, "owner"), Equals(record, "a"))))
        )
    assert deleted == 1


@pytest.mark.asyncio
async def test_canonical_values_round_trip_through_database(database: Database) -> None:
    table = canonical_table()
    row = CanonicalRow(
        record_id="record",
        enabled=True,
        payload={"items": [1, "two"], "active": False},
        labels=("alpha", "beta"),
        document=SampleDocument(label="document"),
    )
    await database.ensure_schema((table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(table, InsertCommand(row=row))
        stored = await session.find_one(table, Query(NoFilter(), AllFields(), Unordered()))
    assert stored == row


@pytest.mark.asyncio
async def test_insert_stores_canonical_snapshot(database: Database) -> None:
    table = canonical_table()
    payload = {"items": ["original"]}
    row = CanonicalRow(
        record_id="record",
        enabled=True,
        payload=payload,
        labels=(),
        document=SampleDocument(label="document"),
    )
    await database.ensure_schema((table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.insert(table, InsertCommand(row=row))
        payload["items"].append("mutated")
        stored = await session.find_one(table, Query(NoFilter(), AllFields(), Unordered()))
    assert stored is not None
    assert stored.payload == {"items": ["original"]}


@pytest.mark.asyncio
async def test_non_json_value_is_rejected_at_database_boundary(database: Database) -> None:
    table = canonical_table()
    row = CanonicalRow(
        record_id="record",
        enabled=True,
        payload={"invalid"},
        labels=(),
        document=SampleDocument(label="document"),
    )
    await database.ensure_schema((table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        with pytest.raises(TypeError, match="JSON-compatible"):
            await session.insert(table, InsertCommand(row=row))


@pytest.mark.parametrize("identifier", ("", "has-dash", "has space", "1starts_with_digit"))
def test_invalid_persistence_identifier_is_rejected(identifier: str) -> None:
    with pytest.raises(ValueError, match="Invalid persistence identifier"):
        TableIdentity(identifier)


def test_neutral_table_identity_accepts_backend_reserved_identifier() -> None:
    assert TableIdentity("sqlite_internal").name == "sqlite_internal"


@pytest.mark.asyncio
async def test_typed_transaction_rolls_back_on_failure(database: Database) -> None:
    table, _, _, _ = make_table()
    await database.ensure_schema((table,))
    with pytest.raises(RuntimeError):
        async with database.session(mode=TransactionMode.READ_WRITE) as session:
            await session.insert(table, InsertCommand(row=make_row("a")))
            raise RuntimeError("rollback")
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        rows = await session.find_many(table, Query(NoFilter(), AllFields(), Unordered()))
    assert rows == ()


@pytest.mark.asyncio
async def test_typed_transaction_rolls_back_on_cancellation(database: Database) -> None:
    table, _, _, _ = make_table()
    await database.ensure_schema((table,))

    async def cancelled_transaction() -> None:
        async with database.session(mode=TransactionMode.READ_WRITE) as session:
            await session.insert(table, InsertCommand(row=make_row("a")))
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await cancelled_transaction()
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        rows = await session.find_many(table, Query(NoFilter(), AllFields(), Unordered()))
    assert rows == ()


@pytest.mark.asyncio
async def test_serialized_writes_serialize_concurrent_upserts(database: Database) -> None:
    table, owner, record, payload = make_table("serialized_samples")
    await database.ensure_schema((table,))

    async def upsert(value: str) -> None:
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(
                table,
                UpsertCommand(
                    key=SampleKey(owner_id="owner", record_id="shared"),
                    row=make_row("shared", value),
                ),
            )
            await asyncio.sleep(0)

    await asyncio.gather(*(upsert(f"value-{index}") for index in range(8)))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        rows = await session.find_many(
            table,
            Query(
                Equals(owner, "owner"),
                AllFields(),
                OrderBy((record,)),
            ),
        )
    assert len(rows) == 1
    assert rows[0].payload.startswith("value-")
