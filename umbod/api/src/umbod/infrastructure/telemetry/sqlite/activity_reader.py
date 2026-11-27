from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import get_args

import aiosqlite

from umbod.core.activity.models import (
    AfterSession,
    HarnessOutcomes,
    HarnessSource,
    HarnessSummary,
    MissingSession,
    RankedTool,
    SessionDetailQuery,
    SessionKey,
    SessionListQuery,
    SessionReport,
    SessionSlice,
    SessionSummary,
)
from umbod.core.activity.ports import ActivitySourceUnavailable
from umbod.core.telemetry.analytics import OwnedLog, TelemetryAnalyticsUnavailable, TimeRange

from .database import SqliteAnalyticsRuntime
from .values import from_microseconds, to_microseconds

_HARNESS_SOURCES: tuple[HarnessSource, ...] = get_args(HarnessSource)
_CLIENT_LABELS: dict[str, str] = {
    'claude-code': 'Claude Code',
    'claude-code-desktop': 'Claude Code Desktop',
    'codex': 'Codex',
    'codex_exec': 'Codex CLI',
}
_WHITESPACE = 'char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)'
_SESSION_USABLE = (
    "typeof(session_id) = 'text' AND length(session_id) <= 1024 "
    f"AND session_id NOT IN ('.', '..') AND instr(session_id, char(0)) = 0 "
    f"AND trim(session_id, {_WHITESPACE}) <> ''"
)
_OWNED_EVENTS = (
    'WITH events AS (SELECT source, session_id, occurred_at_us, activity_kind, outcome, tool_name '
    'FROM analytics_logs WHERE owner_id COLLATE BINARY = ? AND source COLLATE BINARY IN (?,?,?,?) '
)
_WINDOW_EVENTS = _OWNED_EVENTS + 'AND occurred_at_us >= ? AND occurred_at_us < ?) '
_SESSION_EVENTS = (
    _OWNED_EVENTS + 'AND source COLLATE BINARY = ? AND session_id COLLATE BINARY = ? '
    f'AND {_SESSION_USABLE}) '
)
_CALL = "activity_kind IN ('tool_call', 'file_read', 'file_edit')"
_OUTCOMES = f"""
    COUNT(*) FILTER (WHERE {_CALL} AND outcome = 'success') AS success,
    COUNT(*) FILTER (WHERE {_CALL} AND outcome = 'failure') AS failure,
    COUNT(*) FILTER (WHERE {_CALL} AND outcome IS NOT 'success' AND outcome IS NOT 'failure') AS unknown
"""
_SKILLS = "COUNT(*) FILTER (WHERE activity_kind = 'skill_activation') AS skill_activations"
_SESSION_TIMES = 'MIN(occurred_at_us) AS first_seen_at_us, MAX(occurred_at_us) AS last_seen_at_us'
_GROUP_SESSIONS = 'GROUP BY source COLLATE BINARY, session_id COLLATE BINARY'
_SESSION_COLUMNS = f'source COLLATE BINARY AS source, session_id COLLATE BINARY AS session_id, {_SESSION_TIMES}, {_OUTCOMES}'
_PAST_POSITION = (
    '(last_seen_at_us < ? OR (last_seen_at_us = ? AND '
    '(source COLLATE BINARY, session_id COLLATE BINARY) > (?, ?)))'
)
_TOP_LIMIT = 5
_FAILED_LIMIT = 100

type SqlParameters = tuple[int | str, ...]


class SqliteHarnessActivityReader:
    def __init__(self, runtime: SqliteAnalyticsRuntime) -> None:
        self._runtime = runtime

    async def summarize(self, owner: OwnedLog, window: TimeRange) -> HarnessSummary:
        async with self._connection(snapshot=True) as connection:
            owner = OwnedLog.model_validate(owner.model_dump())
            window = TimeRange.model_validate(window.model_dump())
            parameters = _window_parameters(owner, window)
            async with connection.execute(
                _WINDOW_EVENTS + f'SELECT {_OUTCOMES}, {_SKILLS} FROM events', parameters,
            ) as cursor:
                totals = (await cursor.fetchall())[0]
            return HarnessSummary(
                outcomes=_outcomes(totals),
                top_tools=await _ranked_tools(connection, _WINDOW_EVENTS, parameters, failed_only=False, limit=_TOP_LIMIT),
                skill_activations=totals['skill_activations'],
            )

    async def list_sessions(self, query: SessionListQuery) -> SessionSlice:
        async with self._connection(snapshot=False) as connection:
            query = SessionListQuery.model_validate(query.model_dump())
            statement = (
                _WINDOW_EVENTS
                + f', sessions AS (SELECT {_SESSION_COLUMNS} FROM events WHERE {_SESSION_USABLE} {_GROUP_SESSIONS}) '
                'SELECT * FROM sessions'
            )
            parameters = _window_parameters(query.owner, query.window)
            filters: list[str] = []
            if query.search:
                await connection.create_function('activity_session_matches', 4, _session_matches, deterministic=True)
                filters.append('activity_session_matches(session_id, source, first_seen_at_us, ?)')
                parameters += (query.search.casefold(),)
            if isinstance(query.start, AfterSession):
                position = query.start.position
                last_seen = to_microseconds(position.last_seen_at)
                filters.append(_PAST_POSITION)
                parameters += (last_seen, last_seen, position.key.source, position.key.session_id)
            if filters:
                statement += ' WHERE ' + ' AND '.join(filters)
            statement += ' ORDER BY last_seen_at_us DESC, source COLLATE BINARY ASC, session_id COLLATE BINARY ASC LIMIT ?'
            async with connection.execute(statement, (*parameters, query.limit + 1)) as cursor:
                rows = await cursor.fetchall()
            return SessionSlice(
                sessions=tuple(_session(row) for row in rows[:query.limit]),
                has_more=len(rows) > query.limit,
            )

    async def get_session(self, query: SessionDetailQuery) -> SessionReport | MissingSession:
        async with self._connection(snapshot=True) as connection:
            query = SessionDetailQuery.model_validate(query.model_dump())
            parameters = (query.owner.owner_id, *_HARNESS_SOURCES, query.key.source, query.key.session_id)
            async with connection.execute(
                _SESSION_EVENTS + f'SELECT {_SESSION_COLUMNS}, {_SKILLS} FROM events {_GROUP_SESSIONS}', parameters,
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return MissingSession(kind='missing')
            failed_tools = await _ranked_tools(
                connection, _SESSION_EVENTS, parameters, failed_only=True, limit=_FAILED_LIMIT + 1,
            )
            return SessionReport(
                session=_session(row),
                top_tools=await _ranked_tools(connection, _SESSION_EVENTS, parameters, failed_only=False, limit=_TOP_LIMIT),
                failed_tools=failed_tools[:_FAILED_LIMIT],
                has_more_failed_tools=len(failed_tools) > _FAILED_LIMIT,
                skill_activations=row['skill_activations'],
            )

    @asynccontextmanager
    async def _connection(self, *, snapshot: bool) -> AsyncIterator[aiosqlite.Connection]:
        try:
            async with self._runtime.connection() as connection:
                if snapshot:
                    async with connection.execute('BEGIN'):
                        pass
                yield connection
        except TelemetryAnalyticsUnavailable:
            raise ActivitySourceUnavailable('Harness activity is unavailable') from None


def _window_parameters(owner: OwnedLog, window: TimeRange) -> SqlParameters:
    return (owner.owner_id, *_HARNESS_SOURCES, to_microseconds(window.start), to_microseconds(window.end))


def _session_matches(session_id: str, source: str, first_seen_at_us: int, search: str) -> bool:
    return any(search in value.casefold() for value in _session_search_values(session_id, source, first_seen_at_us))


def _session_search_values(session_id: str, source: str, first_seen_at_us: int) -> Iterable[str]:
    yield session_id
    yield source
    yield _CLIENT_LABELS[source]
    yield from_microseconds(first_seen_at_us).date().isoformat()


def _outcomes(row: aiosqlite.Row) -> HarnessOutcomes:
    return HarnessOutcomes(success=row['success'], failure=row['failure'], unknown=row['unknown'])


def _session(row: aiosqlite.Row) -> SessionSummary:
    return SessionSummary(
        key=SessionKey(source=row['source'], session_id=row['session_id']),
        first_seen_at=from_microseconds(row['first_seen_at_us']),
        last_seen_at=from_microseconds(row['last_seen_at_us']),
        outcomes=_outcomes(row),
    )


async def _ranked_tools(
    connection: aiosqlite.Connection, scope: str, parameters: SqlParameters, *, failed_only: bool, limit: int,
) -> tuple[RankedTool, ...]:
    statement = (
        scope + f"SELECT tool_name, COUNT(*) AS calls FROM events WHERE {_CALL} "
        f"AND typeof(tool_name) = 'text' AND trim(tool_name, {_WHITESPACE}) <> '' "
    )
    if failed_only:
        statement += "AND outcome = 'failure' "
    statement += 'GROUP BY tool_name COLLATE BINARY ORDER BY calls DESC, tool_name COLLATE BINARY ASC LIMIT ?'
    async with connection.execute(statement, (*parameters, limit)) as cursor:
        rows = await cursor.fetchall()
    return tuple(RankedTool(tool_name=row['tool_name'], count=row['calls']) for row in rows)
