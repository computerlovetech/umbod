import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite
import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.persistence import PersistenceBusyError
from umbod.core.usage.models import OwnedUsageQuery, UsageBatch, UsageKind, UsageOutcome, UsageRecord
from umbod.core.usage.store import DatabaseUsageStore


OWNER = "a" * 64
AS_OF = datetime(2026, 5, 10, tzinfo=timezone.utc)


def batch() -> UsageBatch:
    return UsageBatch(records=(UsageRecord(
        event_id=uuid4(), owner_id=OWNER,
        occurred_at_unix_nano=int(AS_OF.timestamp()) * 1_000_000_000,
        observed_at_unix_nano=int(AS_OF.timestamp()) * 1_000_000_000,
        kind=UsageKind.TOOL, outcome=UsageOutcome.SUCCESS, duration_ms=1.0,
        service_name="umbod-test", trace_id="", span_id="",
    ),))


@pytest.mark.asyncio
async def test_usage_survives_runtime_restart_and_replay(tmp_path: Path) -> None:
    path = tmp_path / "usage.sqlite"
    first = await prepared_sqlite_runtime(path)
    observed = batch()
    try:
        await DatabaseUsageStore(first.database).append_usage(observed)
    finally:
        await first.shutdown()
    second = await prepared_sqlite_runtime(path)
    try:
        store = DatabaseUsageStore(second.database)
        await store.append_usage(observed)
        summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
        assert summary.totals.tool.success == 1
    finally:
        await second.shutdown()


@pytest.mark.asyncio
async def test_rollup_failure_rolls_back_ledger_and_can_be_retried(tmp_path: Path) -> None:
    path = tmp_path / "atomic.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with aiosqlite.connect(path) as connection:
            await connection.execute(
                "CREATE TRIGGER reject_usage_rollup BEFORE INSERT ON personal_usage_daily "
                "BEGIN SELECT RAISE(ABORT, 'test rollup failure'); END"
            )
            await connection.commit()
        store = DatabaseUsageStore(runtime.database)
        observed = batch()
        with pytest.raises(aiosqlite.IntegrityError, match="test rollup failure"):
            await store.append_usage(observed)
        async with aiosqlite.connect(path) as connection:
            cursor = await connection.execute("SELECT count(*) FROM personal_usage_events")
            assert await cursor.fetchone() == (0,)
            await cursor.close()
            await connection.execute("DROP TRIGGER reject_usage_rollup")
            await connection.commit()
        await store.append_usage(observed)
        summary = await store.count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
        assert summary.totals.total == 1
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_independent_runtimes_preserve_rollups_when_busy_batches_are_retried(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.sqlite"
    first = await prepared_sqlite_runtime(path)
    second = await prepared_sqlite_runtime(path)
    try:
        stores = (DatabaseUsageStore(first.database), DatabaseUsageStore(second.database))
        batches = tuple(batch() for _ in range(12))
        results = await asyncio.gather(
            *(stores[index % 2].append_usage(observed) for index, observed in enumerate(batches)),
            return_exceptions=True,
        )
        for index, result in enumerate(results):
            if isinstance(result, PersistenceBusyError):
                await stores[index % 2].append_usage(batches[index])
            elif isinstance(result, BaseException):
                raise result
        summary = await stores[0].count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=AS_OF))
        assert summary.totals.total == 12
    finally:
        await first.shutdown()
        await second.shutdown()


@pytest.mark.asyncio
async def test_usage_retention_and_owner_date_indexes_exist(tmp_path: Path) -> None:
    path = tmp_path / "indexes.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with aiosqlite.connect(path) as connection:
            for table, expected in (
                ("personal_usage_events", {("day",), ("owner_id", "day"), ("event_id",)}),
                ("personal_usage_daily", {("day",), ("owner_id", "day", "kind", "outcome")}),
            ):
                cursor = await connection.execute(f"PRAGMA index_list('{table}')")
                indexes = await cursor.fetchall()
                await cursor.close()
                fields = set()
                for index in indexes:
                    cursor = await connection.execute(f"PRAGMA index_info('{index[1]}')")
                    fields.add(tuple(row[2] for row in await cursor.fetchall()))
                    await cursor.close()
                assert expected <= fields
                cursor = await connection.execute(
                    f"EXPLAIN QUERY PLAN DELETE FROM {table} WHERE day < ?", (1,),
                )
                plan = await cursor.fetchall()
                await cursor.close()
                assert any("SEARCH" in row[3] and "day_idx" in row[3] for row in plan)
                cursor = await connection.execute(
                    f"EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE owner_id = ? AND day IN (?, ?)",
                    (OWNER, 1, 2),
                )
                plan = await cursor.fetchall()
                await cursor.close()
                assert any("SEARCH" in row[3] and "owner_id=? AND day=?" in row[3] for row in plan)
    finally:
        await runtime.shutdown()
