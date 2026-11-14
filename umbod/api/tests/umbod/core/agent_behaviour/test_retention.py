import asyncio

import pytest

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.agent_behaviour.retention import DiagnosticRetention
from umbod.core.diagnostics import ApplicationFailureKind


class RetentionDriver:
    def __init__(self) -> None:
        self.calls = 0
        self.intervals: list[float] = []
        self.waiting = asyncio.Event()
        self.tick = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.stopped = asyncio.Event()
        self.fail = False
        self.remaining = 0

    async def purge(self) -> int:
        self.calls += 1
        self.cleaned.set()
        if self.fail:
            raise RuntimeError("private-report-evidence")
        removed = min(100, self.remaining)
        self.remaining -= removed
        return removed

    async def wait(self, seconds: float) -> None:
        self.intervals.append(seconds)
        self.waiting.set()
        try:
            await self.tick.wait()
            self.tick.clear()
        except asyncio.CancelledError:
            self.stopped.set()
            raise


@pytest.mark.asyncio
async def test_cleanup_runs_on_startup_and_stops_before_lifespan_returns() -> None:
    driver = RetentionDriver()
    failures = CapturingApplicationFailures()
    runtime = DiagnosticRetention(driver.purge, failures, driver.wait)
    async with runtime.lifespan():
        assert driver.calls == 1
        await asyncio.wait_for(driver.waiting.wait(), timeout=1)
    assert driver.stopped.is_set()
    assert failures.events == []


@pytest.mark.asyncio
async def test_cleanup_repeats_only_after_hourly_wait() -> None:
    driver = RetentionDriver()
    runtime = DiagnosticRetention(driver.purge, CapturingApplicationFailures(), driver.wait)
    async with runtime.lifespan():
        await asyncio.wait_for(driver.waiting.wait(), timeout=1)
        driver.cleaned.clear()
        driver.tick.set()
        await asyncio.wait_for(driver.cleaned.wait(), timeout=1)
        assert driver.calls == 2
        assert all(interval == 3600 for interval in driver.intervals)


@pytest.mark.asyncio
async def test_cleanup_failure_is_sanitized_and_does_not_prevent_startup() -> None:
    driver = RetentionDriver()
    driver.fail = True
    failures = CapturingApplicationFailures()
    runtime = DiagnosticRetention(driver.purge, failures, driver.wait)
    async with runtime.lifespan():
        assert len(failures.events) == 1
        assert failures.events[0].kind is ApplicationFailureKind.AGENT_BEHAVIOUR_RETENTION
        assert "private-report-evidence" not in failures.events[0].model_dump_json()


@pytest.mark.asyncio
async def test_cleanup_drains_backlog_larger_than_one_transaction_before_idle_wait() -> None:
    driver = RetentionDriver()
    driver.remaining = 251
    runtime = DiagnosticRetention(driver.purge, CapturingApplicationFailures(), driver.wait)
    async with runtime.lifespan():
        assert driver.remaining == 0
        assert driver.calls == 4
        await asyncio.wait_for(driver.waiting.wait(), timeout=1)
        assert driver.intervals == [3600]


@pytest.mark.asyncio
async def test_failed_cleanup_retries_after_one_minute_instead_of_waiting_an_hour() -> None:
    driver = RetentionDriver()
    driver.fail = True
    runtime = DiagnosticRetention(driver.purge, CapturingApplicationFailures(), driver.wait)
    async with runtime.lifespan():
        await asyncio.wait_for(driver.waiting.wait(), timeout=1)
        assert driver.intervals == [60]
