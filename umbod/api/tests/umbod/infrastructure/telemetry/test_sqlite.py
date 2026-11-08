import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest
from pydantic import ValidationError

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    DimensionFilter,
    DimensionGroup,
    FixedTimeBuckets,
    InstanceScope,
    LogCountQuery,
    PaginationQuery,
    LogDimension,
    LogWriteBatch,
    NoTimeBuckets,
    OwnedLog,
    PresentDimensionValue,
    TelemetryAnalyticsUnavailable,
    TimeRange,
    UnownedLog,
)
from umbod.infrastructure.telemetry.composition import (
    create_disabled_analytics_runtime,
    create_sqlite_analytics_runtime,
)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def query() -> LogCountQuery:
    return LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=EPOCH - timedelta(days=1), end=EPOCH + timedelta(days=1)
        ),
        filters=(),
        group_by=(),
        bucketing=NoTimeBuckets(kind="none"),
        pagination={"limit": 1000, "offset": 0},
    )


@pytest.fixture
def batch() -> LogWriteBatch:
    return LogWriteBatch(
        records=(
            AnalyticsLogRecord(
                occurred_at=EPOCH - timedelta(microseconds=1),
                owner=OwnedLog(kind="owned", owner_id="owner"),
                dimensions=(
                    DimensionGroup(
                        dimension=LogDimension.SOURCE,
                        value=PresentDimensionValue(
                            kind="present", value="'; DROP TABLE analytics_logs; --"
                        ),
                    ),
                ),
            ),
            AnalyticsLogRecord(
                occurred_at=EPOCH + timedelta(microseconds=1),
                owner=UnownedLog(kind="unowned"),
                dimensions=(),
            ),
        )
    )


@pytest.mark.asyncio
async def test_invalid_query_is_rejected_before_filesystem_io(
    tmp_path: Path, query: LogCountQuery
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    invalid = query.model_copy(update={"pagination": PaginationQuery.model_construct(limit=0, offset=0)})
    with pytest.raises(
        TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"
    ):
        await runtime.create_reader().count_logs(invalid)
    await runtime.shutdown()
    assert not path.exists()


@pytest.mark.asyncio
async def test_invalid_batch_is_rejected_before_filesystem_io(
    tmp_path: Path, batch: LogWriteBatch
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    record = batch.records[0]
    invalid = batch.model_copy(
        update={
            "records": (
                record.model_copy(update={"dimensions": record.dimensions * 2}),
            )
        }
    )
    with pytest.raises(
        TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"
    ):
        await runtime.create_writer().append_logs(invalid)
    await runtime.shutdown()
    assert not path.exists()


@pytest.mark.asyncio
async def test_restart_preserves_records(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    path = tmp_path / "analytics.sqlite3"
    first = create_sqlite_analytics_runtime(path, ())
    reader = first.create_reader()
    writer = first.create_writer()
    try:
        await writer.append_logs(batch)
    finally:
        await first.shutdown()
    second = create_sqlite_analytics_runtime(path, ())
    try:
        await second.ensure_ready()
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await reader.count_logs(query)
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await writer.append_logs(batch)
        result = await second.create_reader().count_logs(query)
    finally:
        await second.shutdown()
    assert result.rows[0].count == 2


@pytest.mark.asyncio
async def test_reader_and_writer_reuse_eagerly_opened_connections(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections: list[aiosqlite.Connection] = []
    connect = aiosqlite.connect

    def tracked_connect(*args: object, **kwargs: object) -> aiosqlite.Connection:
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", tracked_connect)
    runtime = create_sqlite_analytics_runtime(tmp_path / "analytics.sqlite3", ())
    try:
        await runtime.ensure_ready()
        assert len(connections) == 2
        for _ in range(3):
            await runtime.create_writer().append_logs(batch)
            result = await runtime.create_reader().count_logs(query)
        assert result.rows[0].count == 6
        assert len(connections) == 2
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_filter_values_are_not_sql(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    runtime = create_sqlite_analytics_runtime(tmp_path / "analytics.sqlite3", ())
    await runtime.create_writer().append_logs(batch)
    filtered = query.model_copy(
        update={
            "filters": (
                DimensionFilter(
                    dimension=LogDimension.SOURCE,
                    values=("'; DROP TABLE analytics_logs; --",),
                ),
            )
        }
    )
    result = await runtime.create_reader().count_logs(filtered)
    assert result.rows[0].count == 1
    result = await runtime.create_reader().count_logs(query)
    await runtime.shutdown()
    assert result.rows[0].count == 2


@pytest.mark.asyncio
async def test_negative_microsecond_buckets_floor_in_sqlite(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    runtime = create_sqlite_analytics_runtime(tmp_path / "analytics.sqlite3", ())
    await runtime.create_writer().append_logs(batch)
    result = await runtime.create_reader().count_logs(
        query.model_copy(
            update={
                "bucketing": FixedTimeBuckets(kind="fixed", width="minute"),
            }
        )
    )
    await runtime.shutdown()
    assert [row.bucket.start for row in result.rows] == [
        EPOCH - timedelta(minutes=1),
        EPOCH,
    ]


@pytest.mark.asyncio
async def test_application_database_is_not_modified(
    tmp_path: Path, batch: LogWriteBatch
) -> None:
    application = tmp_path / "application.sqlite3"
    async with aiosqlite.connect(application) as connection:
        await connection.execute("CREATE TABLE application_data (value TEXT)")
        await connection.execute("INSERT INTO application_data VALUES ('unchanged')")
        await connection.commit()
    before = application.read_bytes()
    runtime = create_sqlite_analytics_runtime(
        tmp_path / "analytics.sqlite3", (application,)
    )
    await runtime.create_writer().append_logs(batch)
    await runtime.shutdown()
    assert application.read_bytes() == before


@pytest.mark.parametrize(
    "alias_kind", ["same", "symlink", "hardlink", "sidecar", "symlink_sidecar"]
)
def test_rejects_application_aliases(tmp_path: Path, alias_kind: str) -> None:
    application = tmp_path / "application.sqlite3"
    application.touch()
    alias = tmp_path / "analytics.sqlite3"
    if alias_kind == "same":
        alias = application
    elif alias_kind == "symlink":
        alias.symlink_to(application)
    elif alias_kind == "hardlink":
        alias.hardlink_to(application)
    elif alias_kind == "symlink_sidecar":
        application_alias = tmp_path / "application-alias.sqlite3"
        application_alias.symlink_to(application)
        alias = Path(str(application_alias) + "-wal")
        application = application_alias
    else:
        alias = Path(str(application) + "-wal")
    with pytest.raises(ValueError, match="separate"):
        create_sqlite_analytics_runtime(alias, (application,))


@pytest.mark.parametrize(
    "path", [Path("."), Path(":memory:"), Path("file:analytics.sqlite3")]
)
def test_rejects_non_file_database_paths(path: Path) -> None:
    with pytest.raises(ValueError, match="file-backed"):
        create_sqlite_analytics_runtime(path, ())


@pytest.mark.asyncio
async def test_unknown_database_is_not_adopted(tmp_path: Path) -> None:
    path = tmp_path / "other.sqlite3"
    async with aiosqlite.connect(path) as connection:
        await connection.execute("CREATE TABLE application_data (value TEXT)")
        await connection.commit()
    before = path.read_bytes()
    runtime = create_sqlite_analytics_runtime(path, ())
    with pytest.raises(
        TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"
    ):
        await runtime.ensure_ready()
    await runtime.shutdown()
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_failed_readiness_can_retry(tmp_path: Path, query: LogCountQuery) -> None:
    parent = tmp_path / "blocked"
    parent.touch()
    runtime = create_sqlite_analytics_runtime(parent / "analytics.sqlite3", ())
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await runtime.ensure_ready()
    parent.unlink()
    result = await runtime.create_reader().count_logs(query)
    await runtime.shutdown()
    assert result.rows[0].count == 0


@pytest.mark.asyncio
async def test_concurrent_readiness_reads_and_writes(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    runtime = create_sqlite_analytics_runtime(tmp_path / "analytics.sqlite3", ())
    await asyncio.gather(
        *(runtime.ensure_ready() for _ in range(5)),
        *(runtime.create_writer().append_logs(batch) for _ in range(5)),
        *(runtime.create_reader().count_logs(query) for _ in range(5)),
    )
    result = await runtime.create_reader().count_logs(query)
    await runtime.shutdown()
    assert result.rows[0].count == 10


@pytest.mark.asyncio
async def test_shutdown_prevents_later_io(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    await runtime.shutdown()
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await runtime.ensure_ready()
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await runtime.create_reader().count_logs(query)
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await runtime.create_writer().append_logs(batch)
    assert not path.exists()


@pytest.mark.asyncio
async def test_batch_transaction_rolls_back_on_sql_failure(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    await runtime.ensure_ready()
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            "CREATE TRIGGER reject_unowned BEFORE INSERT ON analytics_logs "
            "WHEN NEW.owner_id IS NULL BEGIN SELECT RAISE(ABORT, 'private error'); END"
        )
        await connection.commit()
    with pytest.raises(
        TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"
    ):
        await runtime.create_writer().append_logs(batch)
    try:
        result = await runtime.create_reader().count_logs(query)
        assert result.rows[0].count == 0
        async with aiosqlite.connect(path) as connection:
            await connection.execute("DROP TRIGGER reject_unowned")
            await connection.commit()
        await runtime.create_writer().append_logs(batch)
        result = await runtime.create_reader().count_logs(query)
        assert result.rows[0].count == 2
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_corrupt_schema_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    await runtime.ensure_ready()
    await runtime.shutdown()
    async with aiosqlite.connect(path) as connection:
        await connection.execute("DROP TABLE analytics_logs")
        await connection.execute("CREATE TABLE analytics_logs (wrong TEXT)")
        await connection.commit()
    restarted = create_sqlite_analytics_runtime(path, ())
    with pytest.raises(
        TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"
    ):
        await restarted.ensure_ready()
    await restarted.shutdown()


@pytest.mark.asyncio
async def test_corrupt_database_errors_are_safe(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    path.write_bytes(b"not a sqlite database")
    runtime = create_sqlite_analytics_runtime(path, ())
    with pytest.raises(
        TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"
    ):
        await runtime.ensure_ready()
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_disabled_runtime_performs_no_io(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    runtime = create_disabled_analytics_runtime()
    await runtime.ensure_ready()
    await runtime.create_writer().append_logs(batch)
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await runtime.create_reader().count_logs(query)
    await runtime.shutdown()
    assert tuple(tmp_path.iterdir()) == ()


def test_write_records_reject_duplicate_dimensions(batch: LogWriteBatch) -> None:
    record = batch.records[0]
    with pytest.raises(ValidationError, match="unique"):
        AnalyticsLogRecord(
            occurred_at=record.occurred_at,
            owner=record.owner,
            dimensions=record.dimensions * 2,
        )


def test_core_analytics_does_not_import_infrastructure() -> None:
    import ast
    import umbod.core.telemetry.analytics as analytics

    for path in Path(analytics.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        assert not any("infrastructure" in name for name in imports)


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_write(
    tmp_path: Path, batch: LogWriteBatch, query: LogCountQuery
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    await runtime.ensure_ready()
    async with aiosqlite.connect(path) as blocker:
        await blocker.execute("BEGIN IMMEDIATE")
        writing = asyncio.create_task(runtime.create_writer().append_logs(batch))
        for _ in range(20):
            await asyncio.sleep(0)
        stopping = asyncio.create_task(runtime.shutdown())
        for _ in range(20):
            await asyncio.sleep(0)
        assert not stopping.done()
        await blocker.rollback()
        await writing
        await stopping
    restarted = create_sqlite_analytics_runtime(path, ())
    result = await restarted.create_reader().count_logs(query)
    await restarted.shutdown()
    assert result.rows[0].count == 2
