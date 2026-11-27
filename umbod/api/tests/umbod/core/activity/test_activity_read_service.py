from datetime import datetime, timedelta, timezone

import pytest

from umbod.core.activity import ActivityReadService, ActivitySourceUnavailable
from umbod.core.activity.cursor import InvalidSessionCursor
from umbod.core.activity.models import (
    AfterSession, CursorToken, FirstPage, HarnessOutcomes, HarnessSummary, MissingSession, MoreSessions,
    SessionDetailQuery, SessionKey, SessionListQuery, SessionSlice, SessionSummary,
)
from umbod.core.telemetry.analytics.models import TimeRange
from umbod.core.telemetry.analytics.write_models import OwnedLog
from umbod.core.usage.models import OwnedUsageQuery, UsageOwner, UsageSummary, UsageWindowDays
from umbod.core.usage.store import DatabaseUsageStore

from tests.persistence_runtime import prepared_inmemory_runtime


AS_OF = datetime(2026, 5, 11, 1, tzinfo=timezone(timedelta(hours=2)))
OWNER = OwnedLog(kind='owned', owner_id='owner-one')
MCP_OWNER = UsageOwner(kind='owned', owner_id='a' * 64)
NO_OUTCOMES = HarnessOutcomes(success=0, failure=0, unknown=0)


class InMemoryHarness:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.periods: list[tuple[OwnedLog, TimeRange]] = []
        self.queries: list[SessionListQuery] = []
        self.unavailable = unavailable

    async def summarize(self, owner: OwnedLog, window: TimeRange) -> HarnessSummary:
        if self.unavailable:
            raise ActivitySourceUnavailable
        self.periods.append((owner, window))
        return HarnessSummary(outcomes=NO_OUTCOMES, top_tools=(), skill_activations=0)

    async def list_sessions(self, query: SessionListQuery) -> SessionSlice:
        self.queries.append(query)
        if isinstance(query.start, AfterSession):
            return SessionSlice(sessions=(), has_more=False)
        item = SessionSummary(
            key=SessionKey(source='codex', session_id='example'),
            first_seen_at=AS_OF, last_seen_at=AS_OF, outcomes=NO_OUTCOMES,
        )
        return SessionSlice(sessions=(item,), has_more=True)

    async def get_session(self, query: SessionDetailQuery) -> MissingSession:
        return MissingSession(kind='missing')


class UnavailableMcp:
    async def summarize(self, query: OwnedUsageQuery) -> UsageSummary:
        raise ActivitySourceUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize('days', [7, 30])
async def test_overview_anchors_both_sources_to_the_same_utc_days(days: UsageWindowDays) -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        harness = InMemoryHarness()
        usage = DatabaseUsageStore(runtime.database)
        service = ActivityReadService(harness, _McpUsage(usage), lambda: AS_OF)
        overview = await service.get_overview(OWNER, MCP_OWNER, days)
    finally:
        await runtime.shutdown()

    assert overview.harness.status == 'available'
    assert overview.mcp.status == 'available'
    assert harness.periods == [(OWNER, overview.period.window)]
    assert overview.mcp.summary.range.start == overview.period.window.start.date()
    assert overview.mcp.summary.range.end == overview.period.window.end.date()
    assert overview.period.window.end == datetime(2026, 5, 11, tzinfo=timezone.utc)
    assert overview.period.window.end - overview.period.window.start == timedelta(days=days)


class _McpUsage:
    def __init__(self, usage: DatabaseUsageStore) -> None:
        self.usage = usage

    async def summarize(self, query: OwnedUsageQuery) -> UsageSummary:
        return await self.usage.count_usage(query)


@pytest.mark.asyncio
async def test_unavailable_mcp_does_not_hide_an_empty_harness_summary() -> None:
    service = ActivityReadService(InMemoryHarness(), UnavailableMcp(), lambda: AS_OF)
    overview = await service.get_overview(OWNER, MCP_OWNER, 7)

    assert overview.harness.status == 'available'
    assert overview.harness.summary.outcomes == NO_OUTCOMES
    assert overview.mcp.model_dump() == {'status': 'unavailable'}


@pytest.mark.asyncio
async def test_session_cursor_keeps_the_window_when_midnight_passes() -> None:
    times = iter((AS_OF, AS_OF + timedelta(days=1)))
    harness = InMemoryHarness()
    service = ActivityReadService(harness, UnavailableMcp(), times.__next__)
    first = await service.list_sessions(OWNER, 7, ' example ', FirstPage(kind='first'), 20)
    assert isinstance(first.page, MoreSessions)
    second = await service.list_sessions(OWNER, 7, 'example', CursorToken(value=first.page.cursor), 20)

    assert second.period == first.period
    assert harness.queries[1].start == AfterSession(kind='after', position=first.sessions[0].position())
    assert second.page.kind == 'end'


@pytest.mark.asyncio
@pytest.mark.parametrize(('owner', 'days', 'search'), [
    (OwnedLog(kind='owned', owner_id='owner-two'), 7, 'example'),
    (OWNER, 30, 'example'),
    (OWNER, 7, 'other'),
])
async def test_session_cursor_is_bound_to_owner_period_and_search(owner: OwnedLog, days: UsageWindowDays, search: str) -> None:
    harness = InMemoryHarness()
    service = ActivityReadService(harness, UnavailableMcp(), lambda: AS_OF)
    first = await service.list_sessions(OWNER, 7, 'example', FirstPage(kind='first'), 20)
    assert isinstance(first.page, MoreSessions)

    with pytest.raises(InvalidSessionCursor):
        await service.list_sessions(owner, days, search, CursorToken(value=first.page.cursor), 20)
    assert len(harness.queries) == 1
