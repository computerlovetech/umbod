import asyncio
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered
from umbod.core.usage.models import OwnedUsageQuery, UsageBatch, UsageKind, UsageOutcome, UsageRecord
from umbod.core.usage.otel import serialize_usage_otel
from umbod.core.usage.schema import EVENT_TABLE, ROLLUP_TABLE
from umbod.core.usage.store import DatabaseUsageStore


OWNER = "a" * 64
OTHER_OWNER = "b" * 64
AS_OF = datetime(2026, 5, 10, 12, tzinfo=timezone.utc)


def record(owner: str, occurred: datetime, kind: UsageKind, outcome: UsageOutcome) -> UsageRecord:
    nano = int(occurred.timestamp()) * 1_000_000_000
    return UsageRecord(
        event_id=uuid4(), owner_id=owner, occurred_at_unix_nano=nano,
        observed_at_unix_nano=nano, kind=kind, outcome=outcome, duration_ms=2.0,
        service_name="umbod-test", trace_id="", span_id="",
    )


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_replay_counts_each_event_once_and_preserves_canonical_otel(database: Database) -> None:
    store = DatabaseUsageStore(database)
    first = record(OWNER, AS_OF, UsageKind.TOOL, UsageOutcome.SUCCESS)
    batch = UsageBatch(records=(first, first))
    await store.append_usage(batch)
    await store.append_usage(batch)
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
    async with database.read_session() as session:
        ledger = await session.find_many(EVENT_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    assert summary.totals.tool.success == 1
    assert len(ledger) == 1
    assert ledger[0].otel_json == serialize_usage_otel(first)


@pytest.mark.asyncio
async def test_owner_isolation_utc_boundaries_and_zero_filled_dates(database: Database) -> None:
    store = DatabaseUsageStore(database)
    records = (
        record(OWNER, datetime(2026, 5, 4, tzinfo=timezone.utc), UsageKind.RESOURCE, UsageOutcome.FAILURE),
        record(OWNER, datetime(2026, 5, 3, 23, 59, 59, tzinfo=timezone.utc), UsageKind.TOOL, UsageOutcome.SUCCESS),
        record(OWNER, datetime(2026, 5, 11, tzinfo=timezone.utc), UsageKind.PROMPT, UsageOutcome.SUCCESS),
        record(OTHER_OWNER, AS_OF, UsageKind.TOOL, UsageOutcome.SUCCESS),
    )
    await store.append_usage(UsageBatch(records=records))
    query_time = datetime(2026, 5, 11, 1, tzinfo=timezone(timedelta(hours=2)))
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=query_time))
    assert summary.range.start == date(2026, 5, 4)
    assert summary.range.end == date(2026, 5, 11)
    assert summary.as_of == datetime(2026, 5, 10, 23, tzinfo=timezone.utc)
    assert len(summary.daily) == 7
    assert summary.daily[0].counts.resource.failure == 1
    assert all(day.counts.total == 0 for day in summary.daily[1:])
    assert summary.totals.total == 1


@pytest.mark.asyncio
async def test_thirty_day_window_has_exact_rollups_without_truncation(database: Database) -> None:
    store = DatabaseUsageStore(database)
    records = tuple(
        record(OWNER, AS_OF - timedelta(days=offset), kind, outcome)
        for offset in range(31)
        for kind in UsageKind
        for outcome in UsageOutcome
        for _ in range(2)
    )
    await store.append_usage(UsageBatch(records=records))
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=30, as_of=AS_OF))
    assert len(summary.daily) == 30
    assert summary.totals.total == 540
    assert all(day.counts.total == 18 for day in summary.daily)


@pytest.mark.asyncio
async def test_retention_removes_both_tables_but_keeps_cutoff_day(database: Database) -> None:
    store = DatabaseUsageStore(database)
    records = tuple(
        record(OWNER, AS_OF - timedelta(days=offset), UsageKind.TOOL, UsageOutcome.CANCELLED)
        for offset in (0, 1, 2)
    )
    await store.append_usage(UsageBatch(records=records))
    await store.prune_usage(date(2026, 5, 9))
    async with database.read_session() as session:
        ledger = await session.find_many(EVENT_TABLE, Query(NoFilter(), AllFields(), Unordered()))
        rollups = await session.find_many(ROLLUP_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    assert {row.day for row in ledger} == {date(2026, 5, 9).toordinal(), date(2026, 5, 10).toordinal()}
    assert {row.day for row in rollups} == {row.day for row in ledger}
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
    assert summary.totals.tool.cancelled == 2


@pytest.mark.asyncio
async def test_serialized_concurrent_batches_do_not_lose_increments(database: Database) -> None:
    store = DatabaseUsageStore(database)
    batches = tuple(
        UsageBatch(records=(record(OWNER, AS_OF, UsageKind.PROMPT, UsageOutcome.SUCCESS),))
        for _ in range(12)
    )
    await asyncio.gather(*(store.append_usage(batch) for batch in batches))
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
    assert summary.totals.prompt.success == 12
