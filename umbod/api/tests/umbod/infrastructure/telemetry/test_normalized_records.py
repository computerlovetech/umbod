from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import JsonValue, ValidationError

from umbod.core.telemetry.analytics import (
    ArchivedLogWriteBatch,
    LogWriteBatch,
    OwnedLog,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsUnavailable,
    UnownedLog,
)
from umbod.core.telemetry.normalization import NormalizedLogRecord
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime
from umbod.rest.telemetry.normalization import normalize_analytics_logs


@pytest.fixture
def normalized_batch() -> LogWriteBatch:
    payload: dict[str, JsonValue] = {
        "resourceLogs": [
            {
                "schemaUrl": "https://example.invalid/schema?token=PRIVATE_RESOURCE_SCHEMA_URL",
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": "codex_exec"}},
                    {"key": "service.version", "value": {"stringValue": "fixture-version"}},
                    {"key": "user.email", "value": {"stringValue": "PRIVATE_RESOURCE_IDENTITY"}},
                ]},
                "scopeLogs": [{
                    "schemaUrl": "https://PRIVATE_SCOPE_SCHEMA_URL@example.invalid/schema",
                    "scope": {"name": "codex", "version": "fixture-scope"},
                    "logRecords": [{
                        "timeUnixNano": "1000000123",
                        "observedTimeUnixNano": "2000000456",
                        "eventName": "event otel/src/events/session_telemetry.rs:1190",
                        "traceId": "0123456789abcdef0123456789abcdef",
                        "spanId": "0123456789abcdef",
                        "body": {"stringValue": "PRIVATE_BODY_CONTENT"},
                        "attributes": [
                            {"key": "event.name", "value": {"stringValue": "codex.tool_result"}},
                            {"key": "tool_name", "value": {"stringValue": "exec_command"}},
                            {"key": "call_id", "value": {"stringValue": "codex-call"}},
                            {"key": "conversation.id", "value": {"stringValue": "codex-conversation"}},
                            {"key": "session.id", "value": {"stringValue": "codex-session"}},
                            {"key": "mcp.session.id", "value": {"stringValue": "mcp-session"}},
                            {"key": "duration_ms", "value": {"stringValue": "42"}},
                            {"key": "success", "value": {"stringValue": "false"}},
                            {"key": "arguments", "value": {"stringValue": "PRIVATE_TOOL_ARGUMENTS"}},
                            {"key": "output", "value": {"stringValue": "PRIVATE_TOOL_OUTPUT"}},
                            {"key": "skill.name", "value": {"stringValue": "PRIVATE_SKILL_IDENTITY"}},
                            {"key": "mcp_server_origin", "value": {"stringValue": "https://PRIVATE_MCP_ORIGIN/path"}},
                            {"key": "extra", "value": {"stringValue": "PRIVATE_UNKNOWN_ATTRIBUTE"}},
                        ],
                    }],
                }],
            },
            {
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": "claude-code"}},
                ]},
                "scopeLogs": [{"logRecords": [{
                    "timeUnixNano": "3000000789",
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "tool_result"}},
                        {"key": "tool_name", "value": {"stringValue": "Read"}},
                        {"key": "tool_use_id", "value": {"stringValue": "claude-call"}},
                        {"key": "session.id", "value": {"stringValue": "claude-session"}},
                        {"key": "success", "value": {"boolValue": True}},
                    ],
                }]}],
            },
        ],
    }
    return normalize_analytics_logs(payload, datetime(2026, 1, 1, tzinfo=timezone.utc), UnownedLog(kind="unowned"))


@pytest.mark.asyncio
async def test_normalized_records_survive_reopen_with_source_evidence_and_without_content(
    tmp_path: Path, normalized_batch: LogWriteBatch,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        await runtime.create_writer().append_logs(normalized_batch)
    finally:
        await runtime.shutdown()
    reopened = SqliteAnalyticsRuntime(path, ())
    try:
        async with reopened.connection() as connection:
            async with connection.execute(
                "SELECT normalization_json FROM analytics_logs ORDER BY rowid"
            ) as cursor:
                serialized = [row[0] for row in await cursor.fetchall()]
    finally:
        await reopened.shutdown()
    assert [NormalizedLogRecord.model_validate_json(value) for value in serialized] == [
        record.normalization for record in normalized_batch.records
    ]
    assert all("PRIVATE_" not in value for value in serialized)
    for retained in (
        "codex.tool_result", "event otel/src/events/session_telemetry.rs:1190",
        "codex-conversation", "codex-session", "mcp-session", "codex-call",
        "0123456789abcdef0123456789abcdef", "fixture-version", "fixture-scope",
    ):
        assert retained in serialized[0]
    assert "claude-call" in serialized[1]


@pytest.mark.asyncio
async def test_normalized_evidence_and_dimensions_roll_back_together(
    tmp_path: Path, normalized_batch: LogWriteBatch,
) -> None:
    runtime = SqliteAnalyticsRuntime(tmp_path / "analytics.sqlite3", ())
    try:
        async with runtime.connection() as connection:
            await connection.execute(
                "CREATE TRIGGER reject_second_record BEFORE INSERT ON analytics_logs "
                "WHEN NEW.source = 'claude-code' BEGIN SELECT RAISE(ABORT, 'reject'); END"
            )
            await connection.commit()
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtime.create_writer().append_logs(normalized_batch)
        async with runtime.connection() as connection:
            async with connection.execute("SELECT COUNT(*) FROM analytics_logs") as cursor:
                assert (await cursor.fetchone())[0] == 0
            await connection.execute("DROP TRIGGER reject_second_record")
            await connection.commit()
        await runtime.create_writer().append_logs(normalized_batch)
        async with runtime.connection() as connection:
            async with connection.execute(
                "SELECT COUNT(*), COUNT(normalization_json) FROM analytics_logs"
            ) as cursor:
                assert tuple(await cursor.fetchone()) == (2, 2)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_invalid_normalization_schema_is_rejected_before_storage_io(
    tmp_path: Path, normalized_batch: LogWriteBatch,
) -> None:
    record = normalized_batch.records[0]
    invalid = record.model_copy(update={
        "normalization": record.normalization.model_copy(update={"schema_version": 999}),
    })
    path = tmp_path / "analytics.sqlite3"
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        with pytest.warns(UserWarning, match="Pydantic serializer warnings"):
            with pytest.raises(TelemetryAnalyticsUnavailable):
                await runtime.create_writer().append_logs(LogWriteBatch(records=(invalid,)))
    finally:
        await runtime.shutdown()
    assert not path.exists()


@pytest.fixture
def archived_batch(normalized_batch: LogWriteBatch) -> ArchivedLogWriteBatch:
    owner = OwnedLog(kind="owned", owner_id="trusted-owner")
    return ArchivedLogWriteBatch(
        raw_payload=b"\x00archived-private-payload\xff",
        encoding="protobuf",
        received_at=datetime(1970, 1, 1, 1, 0, 1, tzinfo=timezone(timedelta(hours=1))),
        owner=owner,
        records=tuple(record.model_copy(update={"owner": owner}) for record in normalized_batch.records),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_id", ["trusted-owner", None], ids=["owned", "unowned"])
async def test_archived_append_stores_exact_raw_bytes_and_links_normalized_rows_in_order(
    tmp_path: Path, archived_batch: ArchivedLogWriteBatch, normalized_batch: LogWriteBatch,
    owner_id: str | None,
) -> None:
    if owner_id is None:
        archived_batch = ArchivedLogWriteBatch(
            raw_payload=archived_batch.raw_payload,
            encoding="protobuf",
            received_at=archived_batch.received_at,
            owner=UnownedLog(kind="unowned"),
            records=normalized_batch.records,
        )
    runtime = SqliteAnalyticsRuntime(tmp_path / "analytics.sqlite3", ())
    analytics: TelemetryAnalyticsRuntime = runtime
    try:
        await analytics.create_writer().append_logs(archived_batch)
        async with runtime.connection() as connection:
            async with connection.execute(
                "SELECT id, raw_payload, encoding, received_at_us, owner_id FROM analytics_raw_batches"
            ) as cursor:
                (archive,) = await cursor.fetchall()
            async with connection.execute(
                "SELECT raw_batch_id, raw_record_index, owner_id, normalization_json "
                "FROM analytics_logs ORDER BY raw_record_index"
            ) as cursor:
                rows = await cursor.fetchall()
    finally:
        await runtime.shutdown()
    assert tuple(archive[1:]) == (archived_batch.raw_payload, "protobuf", 1_000_000, owner_id)
    assert [tuple(row) for row in rows] == [
        (archive[0], index, owner_id, record.normalization.model_dump_json())
        for index, record in enumerate(archived_batch.records)
    ]


@pytest.mark.asyncio
async def test_rejected_archived_append_rolls_back_raw_batch_and_first_normalized_row(
    tmp_path: Path, archived_batch: ArchivedLogWriteBatch,
) -> None:
    runtime = SqliteAnalyticsRuntime(tmp_path / "analytics.sqlite3", ())
    try:
        async with runtime.connection() as connection:
            await connection.execute(
                "CREATE TRIGGER reject_second_record BEFORE INSERT ON analytics_logs "
                "WHEN NEW.raw_record_index = 1 BEGIN SELECT RAISE(ABORT, 'private error'); END"
            )
            await connection.commit()
        with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
            await runtime.create_writer().append_logs(archived_batch)
        async with runtime.connection() as connection:
            async with connection.execute(
                "SELECT (SELECT COUNT(*) FROM analytics_raw_batches), (SELECT COUNT(*) FROM analytics_logs)"
            ) as cursor:
                assert tuple(await cursor.fetchone()) == (0, 0)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_raw_deletion_keeps_historical_links_and_never_reuses_batch_id(
    tmp_path: Path, archived_batch: ArchivedLogWriteBatch,
) -> None:
    runtime = SqliteAnalyticsRuntime(tmp_path / "analytics.sqlite3", ())
    try:
        await runtime.create_writer().append_logs(archived_batch)
        async with runtime.connection() as connection:
            async with connection.execute("SELECT id FROM analytics_raw_batches") as cursor:
                (first_id,) = await cursor.fetchone()
            await connection.execute("DELETE FROM analytics_raw_batches")
            await connection.commit()
        await runtime.create_writer().append_logs(archived_batch)
        async with runtime.connection() as connection:
            async with connection.execute("SELECT id FROM analytics_raw_batches") as cursor:
                (second_id,) = await cursor.fetchone()
            async with connection.execute(
                "SELECT raw_batch_id FROM analytics_logs ORDER BY raw_batch_id, raw_record_index"
            ) as cursor:
                linked_ids = [row[0] for row in await cursor.fetchall()]
    finally:
        await runtime.shutdown()
    assert second_id > first_id
    assert linked_ids == [first_id, first_id, second_id, second_id]


def test_archive_rejects_wrong_owner_without_disclosing_payload(
    archived_batch: ArchivedLogWriteBatch,
) -> None:
    with pytest.raises(ValidationError, match="trusted owner") as error:
        ArchivedLogWriteBatch.model_validate(
            archived_batch.model_dump() | {"owner": OwnedLog(kind="owned", owner_id="wrong-owner")}
        )
    assert "archived-private-payload" not in str(error.value)
    assert "archived-private-payload" not in repr(error.value)
    assert "archived-private-payload" not in repr(archived_batch)
