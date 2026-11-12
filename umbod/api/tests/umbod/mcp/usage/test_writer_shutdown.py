import asyncio
from datetime import date

import pytest

from umbod.core.usage.models import UsageBatch, UsageRecord
from umbod.mcp.usage.statistics import UsageDropReason, UsageObservations
from umbod.mcp.usage.writer import UsageWriteBehind

from .conftest import UsageHarness


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

    async def prune_usage(self, before: date) -> None:
        pass


def runtime(harness: UsageHarness, writer: CleanupWriter) -> UsageWriteBehind:
    return UsageWriteBehind(
        harness.settings, writer, UsageObservations(harness.failures, lambda: 0.0),
        asyncio.get_running_loop().time, lambda: 1_735_689_600_000_000_000, asyncio.sleep,
    )


@pytest.mark.asyncio
async def test_shutdown_reserves_one_shared_budget_for_drain_and_cancellation(
    harness: UsageHarness, record: UsageRecord,
) -> None:
    harness.settings.shutdown_timeout_seconds = 0.2
    harness.settings.write_timeout_seconds = 5
    writer = CleanupWriter(0.04)
    worker = runtime(harness, writer)
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
    harness: UsageHarness, record: UsageRecord,
) -> None:
    harness.settings.shutdown_timeout_seconds = 0.04
    harness.settings.write_timeout_seconds = 5
    writer = CleanupWriter(0.06)
    worker = runtime(harness, writer)
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
    harness: UsageHarness, record: UsageRecord,
) -> None:
    calls: list[int] = []

    def failing_clock() -> float:
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("worker clock failed")
        return 0.0

    worker = UsageWriteBehind(
        harness.settings, harness.writer, UsageObservations(harness.failures, lambda: 0.0),
        failing_clock, lambda: 1_735_689_600_000_000_000, asyncio.sleep,
    )
    worker.start()
    worker.enqueue(record)
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="worker clock failed"):
        await worker.stop()
    assert not worker.running
