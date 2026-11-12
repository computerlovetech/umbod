import asyncio
from datetime import date
from uuid import UUID

import pytest

from umbod.core.usage.models import UsageRecord
from umbod.mcp.usage.statistics import UsageDropReason, UsageObservations
from umbod.mcp.usage.writer import UsageWriteBehind

from .conftest import UsageHarness


@pytest.mark.asyncio
async def test_queue_drops_newest_without_blocking_and_drains_batches(harness: UsageHarness, record: UsageRecord) -> None:
    harness.runtime.start()
    for index in range(6):
        harness.runtime.enqueue(record.model_copy(update={'event_id': UUID(int=index + 1)}))
    snapshot = harness.runtime.statistics
    await harness.runtime.stop()
    persisted = [item.event_id.int for batch in harness.writer.batches for item in batch.records]
    assert persisted == [1, 2, 3, 4]
    assert all(len(batch.records) <= 2 for batch in harness.writer.batches)
    assert snapshot.accepted == 4
    assert snapshot.persisted == 0
    assert harness.runtime.statistics.persisted == 4
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.OVERFLOW] == 2
    assert len(harness.failures.events) == 1


@pytest.mark.asyncio
async def test_retry_keeps_identical_batch_and_uses_bounded_backoff(harness: UsageHarness, record: UsageRecord) -> None:
    harness.writer.failures_remaining = 3
    harness.runtime.start()
    harness.runtime.enqueue(record)
    await harness.runtime.stop()
    assert harness.delays == [0.25, 1.0, 4.0]
    assert len(harness.writer.batches) == 4
    assert all(batch == harness.writer.batches[0] for batch in harness.writer.batches)
    assert harness.runtime.statistics.persisted == 1


@pytest.mark.asyncio
async def test_exhausted_write_drops_once_without_sensitive_failure_evidence(harness: UsageHarness, record: UsageRecord) -> None:
    harness.writer.failures_remaining = 10
    harness.runtime.start()
    harness.runtime.enqueue(record)
    await harness.runtime.stop()
    assert harness.runtime.statistics.persisted == 0
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.WRITE] == 1
    assert len(harness.writer.batches) == 4
    assert 'SECRET' not in repr(harness.failures.events)
    assert record.owner_id not in repr(harness.failures.events)
    assert 'exception.stacktrace' not in repr(harness.failures.events)


@pytest.mark.asyncio
async def test_shutdown_accounts_for_inflight_and_queued_records(harness: UsageHarness, record: UsageRecord) -> None:
    harness.settings.write_timeout_seconds = 1
    harness.writer.blocked = True
    harness.runtime.start()
    for _ in range(4):
        harness.runtime.enqueue(record)
    await asyncio.wait_for(harness.writer.attempted.wait(), timeout=1)
    await harness.runtime.stop()
    assert not harness.runtime.running
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.SHUTDOWN] == 4
    assert harness.runtime.statistics.persisted == 0
    await harness.runtime.stop()
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.SHUTDOWN] == 4


@pytest.mark.asyncio
async def test_attempt_timeout_retries_and_drops_without_stalling_shutdown(harness: UsageHarness, record: UsageRecord) -> None:
    harness.settings.shutdown_timeout_seconds = 1
    harness.writer.blocked = True
    harness.runtime.start()
    harness.runtime.enqueue(record)
    await harness.runtime.stop()
    assert len(harness.writer.batches) == 4
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.WRITE] == 1


@pytest.mark.asyncio
async def test_oversized_utf8_projection_is_rejected_before_queueing(harness: UsageHarness, record: UsageRecord) -> None:
    harness.settings.max_record_bytes = 256
    harness.runtime.start()
    harness.runtime.enqueue(record)
    await harness.runtime.stop()
    assert harness.runtime.statistics.accepted == 0
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.OVERSIZED] == 1
    assert harness.writer.batches == []


@pytest.mark.asyncio
async def test_startup_prunes_using_utc_retention_boundary(harness: UsageHarness, record: UsageRecord) -> None:
    harness.runtime.start()
    harness.runtime.enqueue(record)
    await harness.runtime.stop()
    assert harness.writer.pruned == [date(2024, 10, 4)]


@pytest.mark.asyncio
async def test_partial_batch_flushes_on_deadline_without_shutdown(harness: UsageHarness, record: UsageRecord) -> None:
    harness.runtime.start()
    try:
        harness.runtime.enqueue(record)
        await asyncio.wait_for(harness.writer.attempted.wait(), timeout=1)
        assert harness.writer.batches[0].records == (record,)
    finally:
        await harness.runtime.stop()


@pytest.mark.asyncio
async def test_retention_runs_again_after_one_day(harness: UsageHarness, record: UsageRecord) -> None:
    monotonic = [0.0]
    runtime = UsageWriteBehind(harness.settings, harness.writer, UsageObservations(harness.failures, lambda: monotonic[0]),
                              lambda: monotonic[0], lambda: 1_735_689_600_000_000_000, asyncio.sleep)
    runtime.start()
    try:
        runtime.enqueue(record)
        runtime.enqueue(record)
        await asyncio.wait_for(harness.writer.attempted.wait(), timeout=1)
        monotonic[0] = 86401
        harness.writer.attempted.clear()
        runtime.enqueue(record)
        runtime.enqueue(record)
        await asyncio.wait_for(harness.writer.attempted.wait(), timeout=1)
    finally:
        await runtime.stop()
    assert len(harness.writer.pruned) == 2


@pytest.mark.asyncio
async def test_disabled_collection_never_starts(harness: UsageHarness) -> None:
    harness.settings.enabled = False
    harness.runtime.start()
    assert not harness.runtime.running
    await harness.runtime.stop()
    assert harness.writer.pruned == []
