from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from umbod.core.activity.models import (
    AfterSession,
    FirstPage,
    HarnessOutcomes,
    MissingSession,
    RankedTool,
    SessionDetailQuery,
    SessionKey,
    SessionListQuery,
    SessionReport,
)
from umbod.core.activity.ports import ActivitySourceUnavailable
from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    DimensionGroup,
    LogDimension,
    LogWriteBatch,
    OwnedLog,
    PresentDimensionValue,
    TimeRange,
    UnownedLog,
)
from umbod.core.telemetry.normalization import UnavailableLogNormalization
from umbod.infrastructure.telemetry.sqlite import activity_reader
from umbod.infrastructure.telemetry.sqlite.activity_reader import SqlParameters, SqliteHarnessActivityReader
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime

pytestmark = pytest.mark.asyncio

_OWNER = OwnedLog(kind='owned', owner_id='owner')
_OTHER_OWNER = OwnedLog(kind='owned', owner_id='other')
_START = datetime(2026, 3, 1, tzinfo=timezone.utc)
_END = _START + timedelta(days=3)
_WINDOW = TimeRange(start=_START, end=_END)


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SqliteAnalyticsRuntime]:
    runtime = SqliteAnalyticsRuntime(tmp_path / 'analytics.sqlite3', ())
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def _log(
    source: str, session_id: str, *, owner: OwnedLog | UnownedLog = _OWNER,
    occurred_at: datetime = _START, **dimensions: str,
) -> AnalyticsLogRecord:
    return AnalyticsLogRecord(
        owner=owner,
        occurred_at=occurred_at,
        normalization=UnavailableLogNormalization(kind='unavailable', reason='legacy_or_unspecified'),
        dimensions=tuple(
            DimensionGroup(dimension=LogDimension(key), value=PresentDimensionValue(kind='present', value=value))
            for key, value in {'source': source, 'session_id': session_id, **dimensions}.items()
        ),
    )


async def test_summary_counts_owned_harness_activity_and_ranks_exact_nonblank_tools(
    runtime: SqliteAnalyticsRuntime,
) -> None:
    await runtime.create_writer().append_logs(LogWriteBatch(records=(
        _log('claude-code', 'a', activity_kind='tool_call', outcome='success', tool_name='edit'),
        _log('claude-code-desktop', 'a', activity_kind='file_read', outcome='failure', tool_name='edit'),
        _log('codex', 'a', activity_kind='file_edit', tool_name='Edit'),
        _log('codex_exec', 'a', activity_kind='tool_call', outcome='unrecognized', tool_name='\t\u00a0'),
        _log('codex_exec', 'a', activity_kind='skill_activation', outcome='failure', tool_name='private skill'),
        _log('codex', 'a', activity_kind='file_read', outcome='success', tool_name=' edit '),
        _log('codex', 'a', activity_kind='file_read', outcome='success', tool_name='a'),
        _log('codex', 'a', activity_kind='file_read', outcome='success', tool_name='b'),
        _log('codex', 'a', activity_kind='file_read', outcome='success', tool_name='c'),
        _log('codex', 'a', outcome='failure', tool_name='not activity'),
        _log('Codex', 'a', activity_kind='tool_call', outcome='failure'),
        _log('codex', 'a', owner=_OTHER_OWNER, activity_kind='tool_call', outcome='failure'),
        _log('codex', 'a', owner=UnownedLog(kind='unowned'), activity_kind='skill_activation'),
        _log('codex', 'a', occurred_at=_END, activity_kind='tool_call', outcome='failure'),
    )))

    summary = await SqliteHarnessActivityReader(runtime).summarize(_OWNER, _WINDOW)

    assert summary.outcomes == HarnessOutcomes(success=5, failure=1, unknown=2)
    assert summary.top_tools == tuple(
        RankedTool(tool_name=name, count=count)
        for name, count in [('edit', 2), (' edit ', 1), ('Edit', 1), ('a', 1), ('b', 1)]
    )
    assert summary.skill_activations == 1


async def test_summary_ranks_tools_from_the_same_snapshot_as_outcomes(
    runtime: SqliteAnalyticsRuntime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = runtime.create_writer()
    await writer.append_logs(LogWriteBatch(records=(
        _log('codex', 'session', activity_kind='tool_call', outcome='success', tool_name='original'),
    )))
    original_ranking = activity_reader._ranked_tools

    async def rank_after_concurrent_write(
        connection: aiosqlite.Connection, scope: str, parameters: SqlParameters, *, failed_only: bool, limit: int,
    ) -> tuple[RankedTool, ...]:
        await writer.append_logs(LogWriteBatch(records=(
            _log('codex', 'session', activity_kind='tool_call', outcome='failure', tool_name='concurrent'),
        )))
        return await original_ranking(connection, scope, parameters, failed_only=failed_only, limit=limit)

    with monkeypatch.context() as patch:
        patch.setattr(activity_reader, '_ranked_tools', rank_after_concurrent_write)
        summary = await SqliteHarnessActivityReader(runtime).summarize(_OWNER, _WINDOW)

    assert summary.outcomes == HarnessOutcomes(success=1, failure=0, unknown=0)
    assert summary.top_tools == (RankedTool(tool_name='original', count=1),)

    refreshed = await SqliteHarnessActivityReader(runtime).summarize(_OWNER, _WINDOW)
    assert refreshed.outcomes.failure == 1


async def test_list_paginates_composite_keys_and_retains_sessions_without_calls(runtime: SqliteAnalyticsRuntime) -> None:
    latest = _START + timedelta(microseconds=7)
    await runtime.create_writer().append_logs(LogWriteBatch(records=(
        _log('claude-code', 'same/path', activity_kind='file_read', outcome='success'),
        _log('claude-code', 'same/path', occurred_at=latest, event_name='ordinary'),
        _log('codex', 'A', occurred_at=latest, event_name='ordinary'),
        _log('codex', 'same/path', occurred_at=latest, activity_kind='skill_activation'),
        _log('codex_exec', 'older', event_name='ordinary'),
        _log('codex', 'foreign', occurred_at=latest, owner=_OTHER_OWNER),
        _log('unknown', 'unsupported', occurred_at=latest),
        _log('codex', 'after', occurred_at=_END),
        _log('codex', 'before', occurred_at=_START - timedelta(microseconds=1)),
        *(_log('codex', invalid, occurred_at=latest) for invalid in ('', '\t\r\n\u00a0', '.', '..', 'X' * 1025, 'a\x00b')),
        _log('codex', 'Z' * 1024),
    )))
    reader = SqliteHarnessActivityReader(runtime)
    query = SessionListQuery(owner=_OWNER, window=_WINDOW, search='', limit=2, start=FirstPage(kind='first'))

    first = await reader.list_sessions(query)
    second = await reader.list_sessions(query.model_copy(update={
        'start': AfterSession(kind='after', position=first.sessions[-1].position()),
    }))
    third = await reader.list_sessions(query.model_copy(update={
        'start': AfterSession(kind='after', position=second.sessions[-1].position()),
    }))

    assert [item.key for item in (*first.sessions, *second.sessions, *third.sessions)] == [
        SessionKey(source='claude-code', session_id='same/path'),
        SessionKey(source='codex', session_id='A'),
        SessionKey(source='codex', session_id='same/path'),
        SessionKey(source='codex', session_id='Z' * 1024),
        SessionKey(source='codex_exec', session_id='older'),
    ]
    assert (first.has_more, second.has_more, third.has_more) == (True, True, False)
    assert first.sessions[0].first_seen_at == _START
    assert first.sessions[0].last_seen_at == latest
    assert first.sessions[0].outcomes == HarnessOutcomes(success=1, failure=0, unknown=0)
    assert first.sessions[1].outcomes == HarnessOutcomes(success=0, failure=0, unknown=0)


@pytest.mark.parametrize('search', ['tÄSK%_', '%_', 'CLAUDE CODE DESKTOP', 'CODE-DESK', '2026-03-01'])
async def test_list_searches_literal_folded_id_source_label_and_first_utc_date(
    runtime: SqliteAnalyticsRuntime, search: str,
) -> None:
    await runtime.create_writer().append_logs(LogWriteBatch(records=(
        _log('claude-code-desktop', 'Täsk%_', occurred_at=_START + timedelta(days=1, microseconds=-1)),
        _log('claude-code-desktop', 'Täsk%_', occurred_at=_START + timedelta(days=2)),
        _log('codex', 'TäskAB', occurred_at=_START + timedelta(days=1)),
    )))
    reader = SqliteHarnessActivityReader(runtime)

    result = await reader.list_sessions(
        SessionListQuery(owner=_OWNER, window=_WINDOW, search=search, limit=10, start=FirstPage(kind='first')),
    )

    assert [session.key.session_id for session in result.sessions] == ['Täsk%_']


async def test_detail_uses_exact_owned_source_key_and_caps_distinct_failed_tools(runtime: SqliteAnalyticsRuntime) -> None:
    earlier = _START - timedelta(days=30)
    await runtime.create_writer().append_logs(LogWriteBatch(records=(
        _log('codex', 'x/y', occurred_at=earlier, event_name='ordinary'),
        _log('codex', 'x/y', occurred_at=_END, activity_kind='skill_activation', tool_name='private skill'),
        _log('codex', 'x/y', activity_kind='file_edit', outcome='failure', tool_name='z'),
        _log('codex', 'x/y', activity_kind='file_read', outcome='failure', tool_name='z'),
        _log('codex', 'x/y', activity_kind='file_read', outcome='success', tool_name='000'),
        _log('codex', 'x/y', activity_kind='tool_call', outcome='failure', tool_name='\n'),
        _log('codex', 'x/y', owner=_OTHER_OWNER, activity_kind='tool_call', outcome='failure', tool_name='foreign'),
        _log('codex_exec', 'x/y', activity_kind='tool_call', outcome='failure', tool_name='wrong source'),
        _log('codex', 'X/y', activity_kind='tool_call', outcome='failure', tool_name='wrong id'),
        *(_log('codex', 'x/y', activity_kind='tool_call', outcome='failure', tool_name=f'{index:03}') for index in range(100)),
    )))
    reader = SqliteHarnessActivityReader(runtime)
    query = SessionDetailQuery(owner=_OWNER, key=SessionKey(source='codex', session_id='x/y'))

    report = await reader.get_session(query)

    assert isinstance(report, SessionReport)
    assert report.session.first_seen_at == earlier
    assert report.session.last_seen_at == _END
    assert report.session.outcomes == HarnessOutcomes(success=1, failure=103, unknown=0)
    assert report.skill_activations == 1
    assert report.top_tools[:2] == (RankedTool(tool_name='000', count=2), RankedTool(tool_name='z', count=2))
    assert report.failed_tools == (
        RankedTool(tool_name='z', count=2),
        *(RankedTool(tool_name=f'{index:03}', count=1) for index in range(99)),
    )
    assert report.has_more_failed_tools


async def test_detail_reports_non_tool_sessions_and_hides_foreign_keys(runtime: SqliteAnalyticsRuntime) -> None:
    await runtime.create_writer().append_logs(LogWriteBatch(records=(
        _log('codex', 'only-log', event_name='ordinary'),
        _log('codex', 'foreign', owner=_OTHER_OWNER, event_name='ordinary'),
    )))
    reader = SqliteHarnessActivityReader(runtime)
    query = SessionDetailQuery(owner=_OWNER, key=SessionKey(source='codex', session_id='only-log'))

    visible = await reader.get_session(query)
    hidden = await reader.get_session(
        query.model_copy(update={'key': SessionKey(source='codex', session_id='foreign')}),
    )

    assert isinstance(visible, SessionReport)
    assert visible.session.outcomes == HarnessOutcomes(success=0, failure=0, unknown=0)
    assert visible.top_tools == visible.failed_tools == ()
    assert not visible.has_more_failed_tools
    assert hidden == MissingSession(kind='missing')


async def test_opening_existing_analytics_storage_adds_the_session_lookup_index(tmp_path: Path) -> None:
    path = tmp_path / 'analytics.sqlite3'
    previous = SqliteAnalyticsRuntime(path, ())
    try:
        await previous.create_writer().append_logs(LogWriteBatch(records=(_log('codex', 'session'),)))
        async with previous.connection() as connection:
            async with connection.execute('DROP INDEX analytics_logs_owner_session'):
                await connection.commit()
    finally:
        await previous.shutdown()

    reopened = SqliteAnalyticsRuntime(path, ())
    try:
        async with reopened.connection() as connection:
            async with connection.execute(
                'EXPLAIN QUERY PLAN ' + activity_reader._SESSION_EVENTS + 'SELECT COUNT(*) FROM events',
                (_OWNER.owner_id, *activity_reader._HARNESS_SOURCES, 'codex', 'session'),
            ) as cursor:
                plan = [row['detail'] for row in await cursor.fetchall()]
        result = await SqliteHarnessActivityReader(reopened).get_session(
            SessionDetailQuery(owner=_OWNER, key=SessionKey(source='codex', session_id='session')),
        )
    finally:
        await reopened.shutdown()

    assert any('SEARCH analytics_logs' in operation and 'analytics_logs_owner_session' in operation for operation in plan)
    assert isinstance(result, SessionReport)


async def test_summary_maps_runtime_shutdown_to_unavailability(runtime: SqliteAnalyticsRuntime) -> None:
    await runtime.shutdown()

    with pytest.raises(ActivitySourceUnavailable):
        await SqliteHarnessActivityReader(runtime).summarize(_OWNER, _WINDOW)


async def test_list_maps_invalid_query_to_unavailability(runtime: SqliteAnalyticsRuntime) -> None:
    query = SessionListQuery(owner=_OWNER, window=_WINDOW, search='', limit=1, start=FirstPage(kind='first'))
    invalid = query.model_copy(update={'limit': 0})

    with pytest.raises(ActivitySourceUnavailable):
        await SqliteHarnessActivityReader(runtime).list_sessions(invalid)
