import asyncio
from dataclasses import replace
from typing import cast
from unittest.mock import create_autospec

import pytest

from umbod.core.persistence import (
    AllFields,
    DatabaseSession,
    Equals,
    NoFilter,
    Query,
    ReadPlan,
    ReadPlanOperations,
    Table,
    Unordered,
)
from tests.support.persistence_contracts import (
    GeneratedRow,
    SampleKey,
    SampleRow,
    generated_table,
    non_reusing_generated_table,
    table as make_table,
)


@pytest.fixture
def plan() -> ReadPlanOperations:
    return ReadPlan()


@pytest.mark.asyncio
async def test_key_generation_policy_participates_in_read_deduplication(
    plan: ReadPlanOperations,
) -> None:
    ordinary, _ = generated_table("same_samples")
    opted_in, _ = non_reusing_generated_table("same_samples")
    equivalent, _ = non_reusing_generated_table("same_samples")
    query: Query[GeneratedRow, GeneratedRow] = Query(NoFilter(), AllFields(), Unordered())
    ordinary_handle = plan.find_many(ordinary, query)
    opted_in_handle = plan.find_many(opted_in, query)
    equivalent_handle = plan.find_many(equivalent, query)
    session = create_autospec(DatabaseSession, instance=True)
    session.find_many.return_value = ()
    results = await plan.execute(session)
    assert session.find_many.await_count == 2
    assert results.get(ordinary_handle) == ()
    assert results.get(opted_in_handle) == results.get(equivalent_handle) == ()


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
