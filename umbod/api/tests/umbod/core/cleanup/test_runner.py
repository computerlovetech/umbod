import asyncio
from collections.abc import Awaitable, Callable

import pytest

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.cleanup import CleanupRunner
from umbod.core.diagnostics import ApplicationFailureKind


class Job:
    failure_kind = ApplicationFailureKind.USAGE_RETENTION

    def __init__(self, operation: Callable[[], Awaitable[None]]) -> None:
        self._operation = operation

    async def run(self) -> None:
        await self._operation()


@pytest.mark.asyncio
async def test_explicit_jobs_run_sequentially_in_registration_order() -> None:
    calls: list[str] = []

    async def first() -> None:
        calls.append("first started")
        await asyncio.sleep(0)
        calls.append("first finished")

    async def second() -> None:
        calls.append("second")

    failures = CapturingApplicationFailures()
    assert await CleanupRunner((Job(first), Job(second)), 1, failures).run()
    assert calls == ["first started", "first finished", "second"]
    assert failures.events == []


@pytest.mark.asyncio
async def test_failure_continues_other_jobs_and_publishes_sanitized_snapshot() -> None:
    calls: list[str] = []

    async def failing() -> None:
        raise RuntimeError("SECRET credential payload")

    async def succeeding() -> None:
        calls.append("finished")

    failures = CapturingApplicationFailures()
    assert not await CleanupRunner((Job(failing), Job(succeeding)), 1, failures).run()
    assert calls == ["finished"]
    assert len(failures.events) == 1
    assert failures.events[0].kind is ApplicationFailureKind.USAGE_RETENTION
    assert "SECRET" not in failures.events[0].model_dump_json()


@pytest.mark.asyncio
async def test_timeout_cleans_up_before_next_job_and_returns_failure() -> None:
    calls: list[str] = []

    async def blocked() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            calls.append("cancelled")

    async def following() -> None:
        calls.append("following")

    failures = CapturingApplicationFailures()
    assert not await CleanupRunner((Job(blocked), Job(following)), 0.01, failures).run()
    assert calls == ["cancelled", "following"]
    assert len(failures.events) == 1


@pytest.mark.asyncio
async def test_cancellation_propagates_without_starting_remaining_jobs() -> None:
    calls: list[str] = []
    started = asyncio.Event()

    async def blocked() -> None:
        started.set()
        await asyncio.Event().wait()

    async def following() -> None:
        calls.append("following")

    failures = CapturingApplicationFailures()
    task = asyncio.create_task(CleanupRunner((Job(blocked), Job(following)), 1, failures).run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == []
    assert failures.events == []
