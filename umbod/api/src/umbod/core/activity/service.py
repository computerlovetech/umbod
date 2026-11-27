from asyncio import gather
from datetime import datetime, time, timedelta, timezone
from typing import Callable

from umbod.core.telemetry.analytics.models import TimeRange
from umbod.core.telemetry.analytics.write_models import OwnedLog
from umbod.core.usage.models import OwnedUsageQuery, UsageOwner, UsageWindowDays

from .cursor import InvalidSessionCursor, decode_session_cursor, encode_session_cursor
from .models import (
    ActivityOverview, ActivityPeriod, AfterSession, CursorToken, FirstPage, HarnessAvailable,
    McpAvailable, MissingSession, MoreSessions, NoMoreSessions, SessionDetailQuery, SessionKey,
    SessionListQuery, SessionPage, SessionReport, SourceUnavailable,
)
from .ports import ActivitySourceUnavailable, HarnessActivityReader, McpActivityReader


def _period(days: UsageWindowDays, as_of: datetime) -> ActivityPeriod:
    utc = as_of.astimezone(timezone.utc)
    end = datetime.combine(utc.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return ActivityPeriod(days=days, as_of=utc, window=TimeRange(start=end - timedelta(days=days), end=end))


class ActivityReadService:
    def __init__(
        self, harness: HarnessActivityReader, mcp: McpActivityReader, now: Callable[[], datetime],
    ) -> None:
        self._harness = harness
        self._mcp = mcp
        self._now = now

    async def get_overview(
        self, harness_owner: OwnedLog, mcp_owner: UsageOwner, days: UsageWindowDays,
    ) -> ActivityOverview:
        period = _period(days, self._now())
        harness, mcp = await gather(self._harness_summary(harness_owner, period), self._mcp_summary(mcp_owner, period))
        return ActivityOverview(period=period, harness=harness, mcp=mcp)

    async def list_sessions(
        self, owner: OwnedLog, days: UsageWindowDays, search: str, cursor: FirstPage | CursorToken, limit: int,
    ) -> SessionPage:
        search = search.strip()
        period, query = self._session_query(owner, days, search, cursor, limit)
        result = await self._harness.list_sessions(query)
        page = MoreSessions(
            kind='more', cursor=encode_session_cursor(owner, period, search, result.sessions[-1].position()),
        ) if result.has_more else NoMoreSessions(kind='end')
        return SessionPage(period=period, sessions=result.sessions, page=page)

    async def get_session(self, owner: OwnedLog, key: SessionKey) -> SessionReport | MissingSession:
        return await self._harness.get_session(SessionDetailQuery(owner=owner, key=key))

    def _session_query(
        self, owner: OwnedLog, days: UsageWindowDays, search: str, cursor: FirstPage | CursorToken, limit: int,
    ) -> tuple[ActivityPeriod, SessionListQuery]:
        if isinstance(cursor, FirstPage):
            period = _period(days, self._now())
            return period, SessionListQuery(owner=owner, window=period.window, search=search, limit=limit, start=cursor)
        decoded = decode_session_cursor(cursor.value, owner, days, search)
        try:
            period = _period(days, decoded.as_of)
        except OverflowError:
            raise InvalidSessionCursor('Invalid session cursor') from None
        if not period.window.start <= decoded.position.last_seen_at < period.window.end:
            raise InvalidSessionCursor('Invalid session cursor position')
        start = AfterSession(kind='after', position=decoded.position)
        return period, SessionListQuery(owner=owner, window=period.window, search=search, limit=limit, start=start)

    async def _harness_summary(self, owner: OwnedLog, period: ActivityPeriod) -> HarnessAvailable | SourceUnavailable:
        try:
            summary = await self._harness.summarize(owner, period.window)
        except ActivitySourceUnavailable:
            return SourceUnavailable(status='unavailable')
        return HarnessAvailable(status='available', summary=summary)

    async def _mcp_summary(self, owner: UsageOwner, period: ActivityPeriod) -> McpAvailable | SourceUnavailable:
        try:
            summary = await self._mcp.summarize(OwnedUsageQuery(owner_id=owner.owner_id, days=period.days, as_of=period.as_of))
        except ActivitySourceUnavailable:
            return SourceUnavailable(status='unavailable')
        return McpAvailable(status='available', summary=summary)
