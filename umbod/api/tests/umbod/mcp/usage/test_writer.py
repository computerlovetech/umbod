import asyncio
from uuid import UUID

import pytest

from umbod.config.usage import PersonalUsageConfig
from umbod.core.usage.models import BuiltinUsageToolTarget, UsageRecord, UsageTool
from umbod.mcp.usage.statistics import UsageDropReason, UsageObservations
from umbod.core.usage.otel import serialize_usage_otel
from umbod.mcp.usage.writer import UsageWriteBehind

from .conftest import FailureCollector, MemoryUsageWriter, UsageHarness


@pytest.mark.asyncio
async def test_canonical_tool_metadata_counts_towards_byte_admission(harness: UsageHarness, record: UsageRecord) -> None:
    tool = UsageTool(
        target=BuiltinUsageToolTarget(kind='builtin', registered_name='x' * 8192),
        tool_name='Files', connector_name='Umbod',
    )
    observed = record.model_copy(update={'tool': tool})
    harness.settings.max_record_bytes = len(serialize_usage_otel(observed).encode('utf-8')) + 1
    harness.runtime.start()
    harness.runtime.enqueue(observed)
    await harness.runtime.stop()
    assert harness.runtime.statistics.accepted == 0
    assert dict(harness.runtime.statistics.dropped)[UsageDropReason.OVERSIZED] == 1
    assert harness.writer.batches == []


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
    failure_evidence = repr(harness.failures.events)
    assert 'SECRET' not in failure_evidence
    assert record.owner_id not in failure_evidence
    assert 'exception.stacktrace' not in failure_evidence


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
async def test_startup_and_shutdown_never_prune_usage(harness: UsageHarness, record: UsageRecord) -> None:
    harness.runtime.start()
    harness.runtime.enqueue(record)
    await harness.runtime.stop()
    assert harness.writer.pruned == []


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
async def test_worker_never_prunes_after_one_day(
    usage_settings: PersonalUsageConfig, usage_writer: MemoryUsageWriter,
    usage_failures: FailureCollector, record: UsageRecord,
) -> None:
    monotonic = [0.0]
    runtime = UsageWriteBehind(
        usage_settings, usage_writer, UsageObservations(usage_failures, lambda: monotonic[0]),
        lambda: monotonic[0], asyncio.sleep,
    )
    runtime.start()
    try:
        runtime.enqueue(record)
        runtime.enqueue(record)
        await asyncio.wait_for(usage_writer.attempted.wait(), timeout=1)
        monotonic[0] = 86401
        usage_writer.attempted.clear()
        runtime.enqueue(record)
        runtime.enqueue(record)
        await asyncio.wait_for(usage_writer.attempted.wait(), timeout=1)
    finally:
        await runtime.stop()
    assert usage_writer.pruned == []


@pytest.mark.asyncio
async def test_disabled_collection_never_starts(harness: UsageHarness) -> None:
    harness.settings.enabled = False
    harness.runtime.start()
    assert not harness.runtime.running
    await harness.runtime.stop()
    assert harness.writer.pruned == []
