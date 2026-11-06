import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypeVar

import pytest
import pytest_asyncio
from pydantic import BaseModel

from umbod.core.persistence import (
    DatabaseSession,
    GeneratedIntegerKeyInsertCommand,
    PersistenceRuntime,
    Table,
    TransactionMode,
)
from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    AnalyticsResultLimitExceeded,
    DimensionFilter,
    DimensionGroup,
    LogCountQuery,
    LogDimension,
    LogWriteBatch,
    MissingDimensionValue,
    OwnedLog,
    OwnersScope,
    PresentDimensionValue,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsUnavailable,
    UnownedLog,
)

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.telemetry_runtime import InMemoryTelemetryAnalyticsRuntime

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)


@pytest_asyncio.fixture
async def persistence() -> AsyncIterator[PersistenceRuntime]:
    runtime = create_inmemory_runtime()
    try:
        await runtime.readiness.ensure_ready()
        yield runtime
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def analytics(persistence: PersistenceRuntime) -> AsyncIterator[TelemetryAnalyticsRuntime]:
    runtime = InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def _record(query: LogCountQuery) -> AnalyticsLogRecord:
    return AnalyticsLogRecord(
        occurred_at=query.time_range.start,
        owner=OwnedLog(kind="owned", owner_id="alice"),
        dimensions=tuple(
            DimensionGroup(
                dimension=dimension,
                value=PresentDimensionValue(kind="present", value=""),
            )
            for dimension in LogDimension
        ),
    )


@pytest.mark.asyncio
async def test_memory_runtime_existing_readers_see_each_append(
    analytics: TelemetryAnalyticsRuntime, query: LogCountQuery,
) -> None:
    reader = analytics.create_reader()
    other_reader = analytics.create_reader()
    writer = analytics.create_writer()
    other_writer = analytics.create_writer()
    assert reader is not other_reader
    assert writer is not other_writer
    assert (await reader.count_logs(query)).rows[0].count == 0
    await analytics.ensure_ready()
    await analytics.ensure_ready()
    await writer.append_logs(LogWriteBatch(records=()))
    batch = LogWriteBatch(records=(_record(query), _record(query)))
    await writer.append_logs(batch)
    assert (await reader.count_logs(query)).rows[0].count == 2
    await other_writer.append_logs(batch)
    assert (await other_reader.count_logs(query)).rows[0].count == 4


@pytest.mark.asyncio
async def test_memory_runtime_preserves_owner_and_all_dimension_states(
    analytics: TelemetryAnalyticsRuntime, query: LogCountQuery,
) -> None:
    present = _record(query)
    missing = present.model_copy(update={
        "owner": UnownedLog(kind="unowned"),
        "dimensions": tuple(
            DimensionGroup(dimension=dimension, value=MissingDimensionValue(kind="missing"))
            for dimension in LogDimension
        ),
    })
    await analytics.create_writer().append_logs(LogWriteBatch(records=(present, missing)))
    reader = analytics.create_reader()
    grouped = query.model_copy(update={"group_by": tuple(LogDimension)})
    result = await reader.count_logs(grouped)
    assert tuple(row.count for row in result.rows) == (1, 1)
    assert result.rows[0].groups == missing.dimensions
    assert result.rows[1].groups == present.dimensions
    owned = grouped.model_copy(update={"scope": OwnersScope(kind="owners", owner_ids=("alice",))})
    assert (await reader.count_logs(owned)).rows == (result.rows[1],)
    filtered = grouped.model_copy(update={"filters": (
        DimensionFilter(dimension=LogDimension.SOURCE, values=("",)),
    )})
    assert (await reader.count_logs(filtered)).rows == (result.rows[1],)
    with pytest.raises(AnalyticsResultLimitExceeded):
        await reader.count_logs(grouped.model_copy(update={"max_groups": 1}))


@pytest.mark.asyncio
async def test_memory_runtime_shutdown_invalidates_handles_without_owning_database(
    persistence: PersistenceRuntime, analytics: TelemetryAnalyticsRuntime,
    query: LogCountQuery,
) -> None:
    reader = analytics.create_reader()
    writer = analytics.create_writer()
    batch = LogWriteBatch(records=(_record(query),))
    await writer.append_logs(batch)
    await analytics.shutdown()
    await analytics.shutdown()
    with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
        await reader.count_logs(query)
    with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
        await writer.append_logs(batch)
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await analytics.ensure_ready()
    fresh = InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)
    try:
        assert (await fresh.create_reader().count_logs(query)).rows[0].count == 1
        await fresh.create_writer().append_logs(batch)
        assert (await fresh.create_reader().count_logs(query)).rows[0].count == 2
    finally:
        await fresh.shutdown()


@pytest.mark.asyncio
async def test_memory_runtime_revalidates_entire_batch_and_query(
    analytics: TelemetryAnalyticsRuntime, query: LogCountQuery,
) -> None:
    valid = _record(query)
    invalid = valid.model_copy(update={"dimensions": valid.dimensions + valid.dimensions})
    writer = analytics.create_writer()
    await writer.append_logs(LogWriteBatch(records=(valid,)))
    invalid_batch = LogWriteBatch(records=(valid,)).model_copy(update={"records": (valid, invalid)})
    with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
        await writer.append_logs(invalid_batch)
    reader = analytics.create_reader()
    assert (await reader.count_logs(query)).rows[0].count == 1
    with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
        await reader.count_logs(query.model_copy(update={"max_groups": 0}))
    assert (await reader.count_logs(query)).rows[0].count == 1


@pytest.mark.asyncio
async def test_memory_runtime_concurrent_facades_append_without_overwriting(
    persistence: PersistenceRuntime, analytics: TelemetryAnalyticsRuntime,
    query: LogCountQuery,
) -> None:
    other = InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)
    try:
        batch = LogWriteBatch(records=(_record(query), _record(query)))
        await asyncio.gather(*(
            runtime.create_writer().append_logs(batch)
            for runtime in (analytics, other) * 10
        ))
        assert (await analytics.create_reader().count_logs(query)).rows[0].count == 40
        assert (await other.create_reader().count_logs(query)).rows[0].count == 40
    finally:
        await other.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError("private diagnostic"), asyncio.CancelledError()])
async def test_memory_runtime_late_insert_failure_rolls_back_entire_batch(
    persistence: PersistenceRuntime, analytics: TelemetryAnalyticsRuntime,
    query: LogCountQuery, monkeypatch: pytest.MonkeyPatch, failure: BaseException,
) -> None:
    original_session = persistence.database.session
    calls = 0

    @asynccontextmanager
    async def failing_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with original_session(mode=mode) as session:
            original_insert = session.insert_generated_integer_key

            async def failing_insert(
                table: Table[RowT, KeyT], command: GeneratedIntegerKeyInsertCommand[RowT],
            ) -> int:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise failure
                return await original_insert(table, command)

            with monkeypatch.context() as session_patch:
                session_patch.setattr(session, "insert_generated_integer_key", failing_insert)
                yield session

    batch = LogWriteBatch(records=(_record(query), _record(query)))
    writer = analytics.create_writer()
    expected = asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else TelemetryAnalyticsUnavailable
    with monkeypatch.context() as database_patch:
        database_patch.setattr(persistence.database, "session", failing_session)
        with pytest.raises(expected) as raised:
            await writer.append_logs(batch)
    assert calls == 2
    if isinstance(raised.value, TelemetryAnalyticsUnavailable):
        assert str(raised.value) == "Telemetry analytics is unavailable"
    reader = analytics.create_reader()
    assert (await reader.count_logs(query)).rows[0].count == 0
    await writer.append_logs(batch)
    assert (await reader.count_logs(query)).rows[0].count == 2


class _FailingReadiness:
    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    async def ensure_ready(self) -> None:
        raise self._failure


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError("private diagnostic"), asyncio.CancelledError()])
async def test_memory_runtime_readiness_failure_preserves_cancellation(
    persistence: PersistenceRuntime, query: LogCountQuery, failure: BaseException,
) -> None:
    runtime = InMemoryTelemetryAnalyticsRuntime(persistence.database, _FailingReadiness(failure))
    expected = asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else TelemetryAnalyticsUnavailable
    try:
        with pytest.raises(expected) as raised:
            await runtime.create_writer().append_logs(LogWriteBatch(records=(_record(query),)))
        if isinstance(raised.value, TelemetryAnalyticsUnavailable):
            assert str(raised.value) == "Telemetry analytics is unavailable"
    finally:
        await runtime.shutdown()
    fresh = InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)
    try:
        assert (await fresh.create_reader().count_logs(query)).rows[0].count == 0
    finally:
        await fresh.shutdown()
