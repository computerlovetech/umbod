import asyncio

import pytest

from umbod.config.usage import PersonalUsageConfig
from umbod.core.usage.models import UsageBatch, UsageRecord
from umbod.mcp.usage.statistics import UsageDropReason, UsageObservations
from umbod.mcp.usage.writer import UsageWriteBehind

from .conftest import FailureCollector, MemoryUsageWriter


class CleanupWriter:
    def __init__(self, cleanup_seconds: float) -> None:
        self.cleanup_seconds = cleanup_seconds
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def append_usage(self, batch: UsageBatch) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup = asyncio.create_task(asyncio.sleep(self.cleanup_seconds))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            self.finished.set()


def runtime(settings: PersonalUsageConfig, writer: CleanupWriter, failures: FailureCollector) -> UsageWriteBehind:
    return UsageWriteBehind(
        settings, writer, UsageObservations(failures, lambda: 0.0),
        asyncio.get_running_loop().time, asyncio.sleep,
    )


@pytest.mark.asyncio
async def test_shutdown_reserves_one_shared_budget_for_drain_and_cancellation(
    usage_settings: PersonalUsageConfig, usage_failures: FailureCollector, record: UsageRecord,
) -> None:
    usage_settings.shutdown_timeout_seconds = 0.2
    usage_settings.write_timeout_seconds = 5
    writer = CleanupWriter(0.04)
    worker = runtime(usage_settings, writer, usage_failures)
    worker.start()
    worker.enqueue(record)
    await asyncio.wait_for(writer.started.wait(), 1)
    started = asyncio.get_running_loop().time()
    await worker.stop()
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.2
    assert writer.finished.is_set()
    assert not worker.running
    assert dict(worker.statistics.dropped)[UsageDropReason.SHUTDOWN] == 1


@pytest.mark.asyncio
async def test_cleanup_overrun_is_reported_only_after_worker_termination(
    usage_settings: PersonalUsageConfig, usage_failures: FailureCollector, record: UsageRecord,
) -> None:
    usage_settings.shutdown_timeout_seconds = 0.04
    usage_settings.write_timeout_seconds = 5
    writer = CleanupWriter(0.06)
    worker = runtime(usage_settings, writer, usage_failures)
    worker.start()
    worker.enqueue(record)
    await asyncio.wait_for(writer.started.wait(), 1)
    with pytest.raises(TimeoutError):
        await worker.stop()
    assert writer.finished.is_set()
    assert not worker.running
    assert dict(worker.statistics.dropped)[UsageDropReason.SHUTDOWN] == 1


@pytest.mark.asyncio
async def test_worker_failure_is_not_hidden_by_shutdown(
    usage_settings: PersonalUsageConfig, usage_writer: MemoryUsageWriter,
    usage_failures: FailureCollector, record: UsageRecord,
) -> None:
    def failing_clock() -> float:
        raise RuntimeError("worker clock failed")

    worker = UsageWriteBehind(
        usage_settings, usage_writer, UsageObservations(usage_failures, lambda: 0.0),
        failing_clock, asyncio.sleep,
    )
    worker.start()
    worker.enqueue(record)
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="worker clock failed"):
        await worker.stop()
    assert not worker.running
