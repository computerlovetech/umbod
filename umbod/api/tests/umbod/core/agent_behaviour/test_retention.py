import asyncio
from datetime import timedelta

import pytest

from umbod.core.agent_behaviour import AgentBehaviourService, PublishConfiguration, SubmitDiagnosticReport
from umbod.core.agent_behaviour.retention import DiagnosticRetention
from umbod.core.agent_behaviour.schema import DEDUPE_TABLE, REPORT_LIST_TABLE, REPORT_TABLE
from umbod.core.callers import CallerContext
from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered

from .conftest import Clock


@pytest.mark.asyncio
async def test_one_shot_expires_reports_then_receipts_at_exact_boundaries(
    service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext,
    submission: SubmitDiagnosticReport, clock: Clock, database: Database,
) -> None:
    await service.publish_configuration(publication)
    await service.submit_report(caller, submission)
    clock.now += timedelta(days=30)
    await DiagnosticRetention(service.purge_expired).run()
    async with database.read_session() as session:
        assert not await session.find_many(REPORT_TABLE, Query(NoFilter(), AllFields(), Unordered()))
        assert not await session.find_many(REPORT_LIST_TABLE, Query(NoFilter(), AllFields(), Unordered()))
        assert len(await session.find_many(DEDUPE_TABLE, Query(NoFilter(), AllFields(), Unordered()))) == 1
    clock.now += timedelta(days=30)
    await DiagnosticRetention(service.purge_expired).run()
    async with database.read_session() as session:
        assert not await session.find_many(DEDUPE_TABLE, Query(NoFilter(), AllFields(), Unordered()))


class RetentionDriver:
    def __init__(self, remaining: int) -> None:
        self.calls = 0
        self.remaining = remaining

    async def purge(self) -> int:
        self.calls += 1
        removed = min(100, self.remaining)
        self.remaining -= removed
        return removed


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining,calls", [(0, 1), (1, 2), (251, 4)])
async def test_cleanup_drains_all_batches_and_returns(remaining: int, calls: int) -> None:
    driver = RetentionDriver(remaining)
    await DiagnosticRetention(driver.purge).run()
    assert driver.calls == calls


@pytest.mark.asyncio
async def test_cleanup_propagates_failure_to_runner() -> None:
    async def purge() -> int:
        raise RuntimeError("private-report-evidence")

    with pytest.raises(RuntimeError):
        await DiagnosticRetention(purge).run()


@pytest.mark.asyncio
async def test_cleanup_propagates_cancellation() -> None:
    async def purge() -> int:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await DiagnosticRetention(purge).run()
