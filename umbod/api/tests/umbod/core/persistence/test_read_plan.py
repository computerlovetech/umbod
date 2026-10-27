import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import ClassVar, cast
from unittest.mock import Mock, create_autospec

import pytest
from pydantic import ConfigDict

from umbod.core.persistence import (
    AllFields,
    ColumnType,
    Database,
    DatabaseSession,
    Equals,
    Fields,
    KeyCodec,
    NoFilter,
    OrderBy,
    Query,
    ReadPlan,
    ReadPlanOperations,
    RowCodec,
    Table,
    TextCodec,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from tests.umbod.core.persistence.contract_support import (
    PayloadResult,
    RecordResult,
    SampleKey,
    SampleRow,
    row as make_row,
    table as make_table,
)


@dataclass
class UnhashableTextCodec:
    delegate: TextCodec
    column_type: ClassVar[ColumnType] = ColumnType.TEXT

    def encode(self, value: str) -> object:
        return self.delegate.encode(value)

    def decode(self, value: object) -> str:
        return self.delegate.decode(value)


class AlternateRow(SampleRow):
    model_config = ConfigDict(frozen=True)


class AlternateRecordResult(RecordResult):
    model_config = ConfigDict(frozen=True)


@pytest.fixture
def plan() -> ReadPlanOperations:
    return ReadPlan()


@asynccontextmanager
async def counted_session(
    database: Database, tables: tuple[Table[SampleRow, SampleKey], ...]
) -> AsyncIterator[tuple[DatabaseSession, Mock]]:
    await database.ensure_schema(tables)
    async with database.session(mode=TransactionMode.READ_WRITE) as delegate:
        counter = create_autospec(DatabaseSession, instance=True)
        counter.find_many.side_effect = delegate.find_many
        counter.find_one.side_effect = delegate.find_one
        yield cast(DatabaseSession, counter), counter


@pytest.mark.asyncio
async def test_registration_performs_no_io_and_deduplicates_equal_reads(
    database: Database, plan: ReadPlanOperations
) -> None:
    table, _, record, _ = make_table()
    equivalent_table, _, equivalent_record, _ = make_table()
    first = plan.find_many(table, Query(Equals(record, "a"), AllFields(), Unordered()))
    second = plan.find_many(
        equivalent_table, Query(Equals(equivalent_record, "a"), AllFields(), Unordered())
    )
    async with counted_session(database, (table,)) as (session, counter):
        assert counter.mock_calls == []
        results = await plan.execute(session)
    assert counter.find_many.await_count == 1
    assert counter.find_one.await_count == 0
    assert results.get(first) == results.get(second) == ()


@pytest.mark.asyncio
async def test_equal_unhashable_descriptors_are_deduplicated(
    database: Database, plan: ReadPlanOperations
) -> None:
    table, _, _, payload = make_table()
    for _ in range(2):
        unhashable_payload = replace(payload, codec=UnhashableTextCodec(TextCodec()))
        descriptor = replace(
            table,
            row_codec=replace(
                table.row_codec, fields=(*table.row_codec.fields[:-1], unhashable_payload)
            ),
        )
        plan.find_many(descriptor, Query(NoFilter(), AllFields(), Unordered()))
    async with counted_session(database, (table,)) as (session, counter):
        await plan.execute(session)
    assert counter.find_many.await_count == 1


@pytest.mark.asyncio
async def test_equal_one_reads_share_execution(database: Database, plan: ReadPlanOperations) -> None:
    table, _, _, _ = make_table()
    query: Query[SampleRow, SampleRow] = Query(NoFilter(), AllFields(), Unordered())
    first = plan.find_one(table, query)
    second = plan.find_one(table, replace(query))
    async with counted_session(database, (table,)) as (session, counter):
        results = await plan.execute(session)
    assert counter.find_one.await_count == 1
    assert results.get(first) is None
    assert results.get(second) is None


@pytest.mark.parametrize(
    "difference",
    ("cardinality", "projection", "result_type", "ordering", "filter", "limit", "table"),
)
@pytest.mark.asyncio
async def test_distinct_reads_are_not_merged(
    database: Database, plan: ReadPlanOperations, difference: str
) -> None:
    table, _, record, payload = make_table()
    other_table, _, other_record, _ = make_table("other_samples")
    query: Query[SampleRow, RecordResult] = Query(
        NoFilter(), Fields(RecordResult, (record,)), Unordered()
    )
    first = plan.find_many(table, query)
    changed_table = table
    changed_query = query
    if difference == "projection":
        changed_query = Query(NoFilter(), Fields(PayloadResult, (payload,)), Unordered())
    elif difference == "result_type":
        changed_query = replace(query, projection=Fields(AlternateRecordResult, (record,)))
    elif difference == "ordering":
        changed_query = replace(query, ordering=OrderBy((record,)))
    elif difference == "filter":
        changed_query = replace(query, filter=Equals(record, "missing"))
    elif difference == "limit":
        changed_query = replace(query, limit=1)
    elif difference == "table":
        changed_table = other_table
        changed_query = replace(query, projection=Fields(RecordResult, (other_record,)))
    if difference == "cardinality":
        second = plan.find_one(changed_table, changed_query)
    else:
        second = plan.find_many(changed_table, changed_query)
    async with counted_session(database, (table, other_table)) as (session, counter):
        results = await plan.execute(session)
    assert counter.find_many.await_count + counter.find_one.await_count == 2
    assert results.get(first) == ()
    assert results.get(second) in ((), None)


@pytest.mark.parametrize("difference", ("row_model", "key_fields"))
@pytest.mark.asyncio
async def test_full_table_descriptor_participates_in_deduplication(
    database: Database, plan: ReadPlanOperations, difference: str
) -> None:
    table, owner, _, _ = make_table()
    changed = (
        replace(table, row_codec=RowCodec(AlternateRow, table.row_codec.fields))
        if difference == "row_model"
        else replace(table, key_codec=KeyCodec(SampleKey, (owner,)))
    )
    query: Query[SampleRow, SampleRow] = Query(NoFilter(), AllFields(), Unordered())
    plan.find_many(table, query)
    plan.find_many(changed, query)
    async with counted_session(database, (table,)) as (session, counter):
        await plan.execute(session)
    assert counter.find_many.await_count == 2


@pytest.mark.asyncio
async def test_projected_and_full_results_and_missing_rows(
    database: Database, plan: ReadPlanOperations
) -> None:
    table, _, record, payload = make_table()
    all_rows = plan.find_many(table, Query(NoFilter(), AllFields(), OrderBy((record,))))
    projected = plan.find_many(
        table, Query(NoFilter(), Fields(PayloadResult, (payload,)), OrderBy((record,)), limit=1)
    )
    existing = plan.find_one(table, Query(Equals(record, "a"), AllFields(), Unordered()))
    missing = plan.find_one(table, Query(Equals(record, "missing"), AllFields(), Unordered()))
    await database.ensure_schema((table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for record_id in ("b", "a"):
            await session.upsert(
                table,
                UpsertCommand(
                    key=SampleKey(owner_id="owner", record_id=record_id), row=make_row(record_id)
                ),
            )
        results = await plan.execute(session)
    assert results.get(all_rows) == (make_row("a"), make_row("b"))
    assert results.get(projected) == (PayloadResult(payload="same"),)
    assert results.get(existing) == make_row("a")
    assert results.get(missing) is None


@pytest.mark.parametrize("cardinality", ("many", "one"))
def test_registration_validates_queries(plan: ReadPlanOperations, cardinality: str) -> None:
    table, _, record, _ = make_table()
    _, foreign, _, _ = make_table("other_samples")
    register = plan.find_many if cardinality == "many" else plan.find_one
    with pytest.raises(ValueError, match="does not belong"):
        register(table, Query(Equals(foreign, "a"), AllFields(), Unordered()))
    with pytest.raises(TypeError, match="expected str"):
        register(table, Query(Equals(record, cast(str, 1)), AllFields(), Unordered()))


@pytest.mark.asyncio
async def test_empty_plan_performs_no_io_and_freezes(plan: ReadPlanOperations) -> None:
    session = create_autospec(DatabaseSession, instance=True)
    await plan.execute(session)
    assert session.mock_calls == []
    table, _, _, _ = make_table()
    query: Query[SampleRow, SampleRow] = Query(NoFilter(), AllFields(), Unordered())
    with pytest.raises(RuntimeError, match="frozen"):
        plan.find_many(table, query)
    with pytest.raises(RuntimeError, match="frozen"):
        plan.find_one(table, query)


@pytest.mark.parametrize("cardinality", ("many", "one"))
@pytest.mark.asyncio
async def test_results_reject_foreign_handles(plan: ReadPlanOperations, cardinality: str) -> None:
    table, _, _, _ = make_table()
    foreign: ReadPlanOperations = ReadPlan()
    query: Query[SampleRow, SampleRow] = Query(NoFilter(), AllFields(), Unordered())
    handle = (
        foreign.find_many(table, query) if cardinality == "many" else foreign.find_one(table, query)
    )
    results = await plan.execute(create_autospec(DatabaseSession, instance=True))
    with pytest.raises(ValueError, match="another plan"):
        results.get(handle)


@pytest.mark.asyncio
async def test_reexecution_reads_fresh_values_without_changing_previous_results(
    database: Database, plan: ReadPlanOperations
) -> None:
    table, _, _, _ = make_table()
    handle = plan.find_many(table, Query(NoFilter(), AllFields(), Unordered()))
    await database.ensure_schema((table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        first = await plan.execute(session)
        await session.upsert(
            table,
            UpsertCommand(key=SampleKey(owner_id="owner", record_id="a"), row=make_row("a")),
        )
        second = await plan.execute(session)
    assert first.get(handle) == ()
    assert second.get(handle) == (make_row("a"),)


@pytest.mark.asyncio
async def test_registration_freezes_before_first_read_finishes_and_cancellation_propagates(
    plan: ReadPlanOperations,
) -> None:
    table, _, _, _ = make_table()
    query: Query[SampleRow, SampleRow] = Query(NoFilter(), AllFields(), Unordered())
    plan.find_many(table, query)
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_read(
        table: Table[SampleRow, SampleKey], query: Query[SampleRow, SampleRow]
    ) -> tuple[SampleRow, ...]:
        started.set()
        await release.wait()
        return ()

    session = create_autospec(DatabaseSession, instance=True)
    session.find_many.side_effect = blocked_read
    task = asyncio.create_task(plan.execute(session))
    await started.wait()
    try:
        with pytest.raises(RuntimeError, match="frozen"):
            plan.find_many(table, query)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert session.find_many.await_count == 1


@pytest.mark.parametrize("failure", (RuntimeError("read failed"), asyncio.CancelledError()))
@pytest.mark.asyncio
async def test_failure_propagates_stops_execution_and_keeps_plan_frozen(
    plan: ReadPlanOperations, failure: BaseException
) -> None:
    table, _, record, _ = make_table()
    query: Query[SampleRow, SampleRow] = Query(NoFilter(), AllFields(), Unordered())
    first = plan.find_many(table, query)
    plan.find_one(table, query)
    plan.find_many(table, replace(query, filter=Equals(record, "a")))
    session = create_autospec(DatabaseSession, instance=True)
    session.find_many.return_value = ()
    session.find_one.side_effect = failure
    with pytest.raises(type(failure)):
        await plan.execute(session)
    assert session.find_many.await_count == 1
    with pytest.raises(RuntimeError, match="frozen"):
        plan.find_many(table, query)
    session.find_one.side_effect = None
    session.find_one.return_value = None
    recovered = await plan.execute(session)
    assert recovered.get(first) == ()
    assert session.find_many.await_count == 3
