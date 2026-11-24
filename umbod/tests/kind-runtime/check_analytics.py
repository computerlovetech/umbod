import asyncio
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from umbod.config import load_server_app_config
from umbod.core.telemetry.analytics import (
    DimensionFilter,
    InstanceScope,
    LogCountQuery,
    LogDimension,
    NoTimeBuckets,
    OwnersScope,
    TimeRange,
)
from umbod.infrastructure import create_configured_analytics_runtime


async def verify_analytics() -> None:
    config = load_server_app_config(".env")
    analytics_path = Path(config.telemetry_analytics.sqlite_path).resolve()
    application_path = Path(config.connector_store.sqlite_path).resolve()
    assert analytics_path != application_path
    runtime = create_configured_analytics_runtime(config)
    try:
        await runtime.ensure_ready()
        query = LogCountQuery(
            scope=InstanceScope(kind="instance"),
            time_range=TimeRange(
                start=datetime(1970, 1, 1, tzinfo=timezone.utc),
                end=datetime(3000, 1, 1, tzinfo=timezone.utc),
            ),
            filters=(DimensionFilter(dimension=LogDimension.SOURCE, values=("umbod-otlp-runtime",)),),
            group_by=(LogDimension.SOURCE,),
            bucketing=NoTimeBuckets(kind="none"),
            pagination={"limit": 10, "offset": 0},
        )
        reader = runtime.create_reader()
        result = await reader.count_logs(query)
        assert result.has_more is False
        assert len(result.rows) == 1
        assert result.rows[0].count == 2
        owner_query = LogCountQuery.model_validate(query.model_dump() | {
            "scope": OwnersScope(kind="owners", owner_ids=("untrusted-client",)),
        })
        assert (await reader.count_logs(owner_query)).rows == ()
    finally:
        await runtime.shutdown()
    archive = sqlite3.connect(analytics_path.as_uri() + "?mode=ro", uri=True)
    try:
        rows = archive.execute(
            "SELECT raw.id, raw.raw_payload, raw.encoding, raw.owner_id, log.raw_record_index, log.normalization_json "
            "FROM analytics_logs AS log JOIN analytics_raw_batches AS raw ON raw.id = log.raw_batch_id "
            "WHERE log.source = ?",
            ("umbod-otlp-runtime",),
        ).fetchall()
        assert len(rows) == 2
        for _, payload, encoding, owner, record_index, normalization in rows:
            assert (encoding, owner, record_index) == ("json", None, 0)
            assert b'"skill.name"' in payload and b'"runtime-fixture-skill"' in payload
            assert json.dumps(json.loads(payload)).encode() == payload
            assert "runtime-fixture-skill" not in normalization
        verify_backfill(archive, rows[0][0])
    finally:
        archive.close()
    connection = sqlite3.connect(application_path.as_uri() + "?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'analytics_logs'"
        ).fetchall() == []
    finally:
        connection.close()


def verify_backfill(archive: sqlite3.Connection, batch_id: int) -> None:
    command = ("umbod", "telemetry", "backfill", "--batch-id", str(batch_id))
    for mode, arguments in (("Preview", command), ("Apply", (*command, "--apply")), ("Apply", (*command, "--apply"))):
        completed = subprocess.run(arguments, capture_output=True, text=True, timeout=20)
        output = completed.stdout + completed.stderr
        selected_batch = f"{mode}: selected 1 batch(es)." in output
        assert completed.returncode == 0, (
            f"Telemetry backfill {mode} exited {completed.returncode}; selected batch: {selected_batch}"
        )
        assert f"{mode} complete: 1 batch(es)." in output
        assert "runtime-fixture-skill" not in output and "skill.name" not in output
    assert archive.execute(
        "SELECT event_name, activity_kind, raw_record_index FROM analytics_logs WHERE raw_batch_id = ?",
        (batch_id,),
    ).fetchall() == [("codex.skill_invocation", "skill_activation", 0)]


if __name__ == "__main__":
    asyncio.run(verify_analytics())
