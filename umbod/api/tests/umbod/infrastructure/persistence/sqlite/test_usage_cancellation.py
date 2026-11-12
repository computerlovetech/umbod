import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite
import pytest
import pytest_asyncio

from tests.support.persistence_contracts import table
from umbod.config.usage import PersonalUsageConfig
from umbod.core.diagnostics import ApplicationFailure
from umbod.mcp.usage.statistics import UsageDropReason, UsageObservations
from umbod.mcp.usage.writer import UsageWriteBehind
from umbod.core.persistence import AllFields, NoFilter, Query, Unordered
from umbod.core.usage.models import OwnedUsageQuery, UsageBatch, UsageKind, UsageOutcome, UsageRecord
from umbod.core.usage.schema import EVENT_TABLE
from umbod.core.usage.store import DatabaseUsageStore
from umbod.infrastructure.connections import ConnectionPool
from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver
from umbod.infrastructure.persistence.schema_preparation import APPLICATION_PERSISTENCE_TABLES
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase


LONG_QUERY = (
    "WITH RECURSIVE numbers(value) AS "
    "(VALUES(0) UNION ALL SELECT value+1 FROM numbers WHERE value<1000000000) "
    "SELECT sum(value) FROM numbers"
)
class FailureCollector:
    def __init__(self) -> None:
        self.events: list[ApplicationFailure] = []

    def send(self, event: ApplicationFailure) -> None:
        self.events.append(event)


def worker(store: DatabaseUsageStore, settings: PersonalUsageConfig) -> UsageWriteBehind:
    clock = asyncio.get_running_loop().time
    return UsageWriteBehind(
        settings, store, UsageObservations(FailureCollector(), clock), clock,
        lambda: (int(AS_OF.timestamp()) + 2 * 86400) * 1_000_000_000, asyncio.sleep,
    )


OWNER = "a" * 64
AS_OF = datetime(2026, 5, 10, tzinfo=timezone.utc)


@dataclass
class SQLiteHarness:
    database: SQLiteDatabase
    connections: ConnectionPool[aiosqlite.Connection]
    connection: aiosqlite.Connection
    path: Path


@pytest_asyncio.fixture
async def sqlite(tmp_path: Path) -> AsyncIterator[SQLiteHarness]:
    path = tmp_path / "cancel.sqlite"
    pool = ConnectionPool(SQLiteConnectionDriver(str(path), create_parent_dirs=False), size=1)
    await pool.initialize()
    database = SQLiteDatabase(pool)
    try:
        await database.ensure_schema(APPLICATION_PERSISTENCE_TABLES)
        async with pool.get_connection() as connection:
            harness = SQLiteHarness(database, pool, connection, path)
        yield harness
    finally:
        await pool.close()


def batch() -> UsageBatch:
    nanos = int(AS_OF.timestamp()) * 1_000_000_000
    return UsageBatch(records=(UsageRecord(
        event_id=uuid4(), owner_id=OWNER, occurred_at_unix_nano=nanos,
        observed_at_unix_nano=nanos, kind=UsageKind.TOOL, outcome=UsageOutcome.SUCCESS,
        duration_ms=1, service_name="test", trace_id="", span_id="",
    ),))


async def watch_statement(connection: aiosqlite.Connection, fragment: str) -> asyncio.Event:
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    def trace(statement: str) -> None:
        if fragment in statement:
            loop.call_soon_threadsafe(started.set)

    await connection.set_trace_callback(trace)
    return started


async def cancel_and_assert_released(task: asyncio.Task[None], sqlite: SQLiteHarness) -> None:
    task.cancel()
    done, _ = await asyncio.wait((task,), timeout=0.5)
    assert task in done
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(0.5):
        async with sqlite.connections.get_connection() as connection:
            assert connection is sqlite.connection
            assert not connection.in_transaction
            cursor = await connection.execute("PRAGMA busy_timeout")
            assert (await cursor.fetchone())[0] == 5000
            await cursor.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("append", "retention"))
async def test_cancelled_usage_sql_interrupts_and_rolls_back_before_pool_reuse(
    sqlite: SQLiteHarness, operation: str,
) -> None:
    store = DatabaseUsageStore(sqlite.database)
    observed = batch()
    if operation == "retention":
        await store.append_usage(observed)
    table = "personal_usage_events" if operation == "retention" else "personal_usage_daily"
    action = "DELETE" if operation == "retention" else "INSERT"
    async with sqlite.database.schema_connection() as connection:
        cursor = await connection.execute(
            f"CREATE TRIGGER slow_usage BEFORE {action} ON {table} BEGIN {LONG_QUERY}; END"
        )
        await cursor.close()
    started = await watch_statement(sqlite.connection, f'{action} ')
    task = asyncio.create_task(
        store.prune_usage(date(2026, 5, 11)) if operation == "retention" else store.append_usage(observed)
    )
    try:
        await asyncio.wait_for(started.wait(), 1)
        await cancel_and_assert_released(task, sqlite)
    finally:
        await sqlite.connection.interrupt()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    async with sqlite.database.schema_connection() as connection:
        cursor = await connection.execute("DROP TRIGGER slow_usage")
        await cursor.close()
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
    assert summary.totals.total == (1 if operation == "retention" else 0)
    async with sqlite.database.read_session() as session:
        ledger = await session.find_many(EVENT_TABLE, Query(NoFilter(), AllFields(), Unordered()))
        assert len(ledger) == summary.totals.total
    await store.append_usage(observed)
    summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
    assert summary.totals.total == 1


@pytest.mark.asyncio
async def test_read_query_cancellation_interrupts_sql_and_reuses_clean_connection(sqlite: SQLiteHarness) -> None:
    records, _, _, _ = table("slow_read")
    async with sqlite.database.schema_connection() as connection:
        cursor = await connection.execute(
            f"CREATE VIEW slow_read AS SELECT 'owner' AS owner_id, 'record' AS record_id, "
            f"CAST(({LONG_QUERY}) AS TEXT) AS payload"
        )
        await cursor.close()
    started = await watch_statement(sqlite.connection, 'FROM "slow_read"')

    async def read() -> None:
        async with sqlite.database.read_session() as session:
            await session.find_many(records, Query(NoFilter(), AllFields(), Unordered()))

    task = asyncio.create_task(read())
    try:
        await asyncio.wait_for(started.wait(), 1)
        await cancel_and_assert_released(task, sqlite)
    finally:
        await sqlite.connection.interrupt()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_schema_query_cancellation_interrupts_sql_and_rolls_back_ddl(sqlite: SQLiteHarness) -> None:
    started = await watch_statement(sqlite.connection, "CREATE TABLE discarded")

    async def prepare() -> None:
        async with sqlite.database.schema_connection() as connection:
            cursor = await connection.execute(f"CREATE TABLE discarded AS {LONG_QUERY}")
            await cursor.close()

    task = asyncio.create_task(prepare())
    try:
        await asyncio.wait_for(started.wait(), 1)
        await cancel_and_assert_released(task, sqlite)
    finally:
        await sqlite.connection.interrupt()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    async with sqlite.connections.get_connection() as connection:
        cursor = await connection.execute("SELECT name FROM sqlite_master WHERE name='discarded'")
        assert await cursor.fetchone() is None
        await cursor.close()


@pytest.mark.asyncio
async def test_worker_stop_interrupts_real_retention_and_finishes_before_persistence_close(sqlite: SQLiteHarness) -> None:
    store = DatabaseUsageStore(sqlite.database)
    await store.append_usage(batch())
    async with sqlite.database.schema_connection() as connection:
        cursor = await connection.execute(
            f"CREATE TRIGGER slow_retention BEFORE DELETE ON personal_usage_events BEGIN {LONG_QUERY}; END"
        )
        await cursor.close()
    started = await watch_statement(sqlite.connection, "DELETE ")
    settings = PersonalUsageConfig(
        shutdown_timeout_seconds=0.3, write_timeout_seconds=5, retention_days=1,
        queue_capacity=4, batch_size=2, flush_interval_seconds=0.001,
    )
    usage = worker(store, settings)
    usage.start()
    stopping: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        for _ in range(3):
            usage.enqueue(batch().records[0])
        before = asyncio.get_running_loop().time()
        stopping = asyncio.create_task(usage.stop())
        done, _ = await asyncio.wait((stopping,), timeout=0.3)
        assert stopping in done
        await stopping
        assert asyncio.get_running_loop().time() - before < 0.3
        assert not usage.running
        assert dict(usage.statistics.dropped)[UsageDropReason.SHUTDOWN] == 3
        async with sqlite.connections.get_connection() as connection:
            assert not connection.in_transaction
        summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
        assert summary.totals.total == 1
        await asyncio.wait_for(sqlite.connections.close(), 0.3)
    finally:
        if stopping is None or not stopping.done():
            await sqlite.connection.interrupt()
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        await usage.stop()


@pytest.mark.asyncio
async def test_retention_attempt_timeout_interrupts_sql_and_allows_next_batch(sqlite: SQLiteHarness) -> None:
    store = DatabaseUsageStore(sqlite.database)
    await store.append_usage(batch())
    async with sqlite.database.schema_connection() as connection:
        cursor = await connection.execute(
            f"CREATE TRIGGER slow_retention BEFORE DELETE ON personal_usage_events BEGIN {LONG_QUERY}; END"
        )
        await cursor.close()
    inserted = await watch_statement(sqlite.connection, 'INSERT INTO "personal_usage_events"')
    settings = PersonalUsageConfig(
        write_timeout_seconds=0.02, shutdown_timeout_seconds=0.5, retention_days=1,
        max_retries=0, batch_size=1, flush_interval_seconds=0.001,
    )
    usage = worker(store, settings)
    usage.start()
    usage.enqueue(batch().records[0])
    try:
        await asyncio.wait_for(inserted.wait(), 0.5)
        await usage.stop()
        assert usage.statistics.persisted == 1
        assert not usage.running
        summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
        assert summary.totals.total == 2
    finally:
        await sqlite.connection.interrupt()
        await usage.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("retries,reason", ((0, UsageDropReason.WRITE), (3, UsageDropReason.SHUTDOWN)))
async def test_sqlite_contention_does_not_hold_usage_worker_in_busy_wait(
    sqlite: SQLiteHarness, retries: int, reason: UsageDropReason,
) -> None:
    settings = PersonalUsageConfig(
        write_timeout_seconds=0.02, shutdown_timeout_seconds=0.1, max_retries=retries,
        batch_size=1, flush_interval_seconds=0.001,
    )
    usage = worker(DatabaseUsageStore(sqlite.database), settings)
    async with aiosqlite.connect(sqlite.path) as blocker:
        await blocker.execute("BEGIN IMMEDIATE")
        usage.start()
        usage.enqueue(batch().records[0])
        stopping = asyncio.create_task(usage.stop())
        try:
            done, _ = await asyncio.wait((stopping,), timeout=0.1)
            assert stopping in done
            await stopping
            assert not usage.running
            assert usage.statistics.persisted == 0
            assert dict(usage.statistics.dropped)[reason] == 1
        finally:
            await blocker.rollback()
            await sqlite.connection.interrupt()
            await asyncio.gather(stopping, return_exceptions=True)
            await usage.stop()
    async with sqlite.connections.get_connection() as connection:
        cursor = await connection.execute("PRAGMA busy_timeout")
        assert (await cursor.fetchone())[0] == 5000
        await cursor.close()
