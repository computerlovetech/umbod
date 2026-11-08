import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue, TypeAdapter

from umbod.core.telemetry.analytics import LogWriteBatch
from umbod.core.telemetry.analytics.projection import project_analytics_log
from umbod.core.telemetry.normalization.models import NormalizationEvidence
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime
from umbod.rest.telemetry.normalization import normalize_analytics_logs


def _producer_payload(name: str) -> dict[str, JsonValue]:
    fixture = Path(__file__).parents[2] / "rest" / "telemetry" / "fixtures" / name
    return cast(dict[str, JsonValue], json.loads(fixture.read_text())["payload"])


def _with_attribute(payload: dict[str, JsonValue], key: str, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    record = cast(dict[str, JsonValue], payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0])
    attributes = cast(list[dict[str, JsonValue]], record["attributes"])
    record["attributes"] = [attribute for attribute in attributes if attribute["key"] != key]
    cast(list[dict[str, JsonValue]], record["attributes"]).append({"key": key, "value": value})
    return payload


@pytest.mark.asyncio
async def test_version_one_evidence_is_unchanged_after_reopen_and_version_two_usage_append(tmp_path: Path) -> None:
    canonical_adapter = TypeAdapter(NormalizationEvidence)
    legacy_path = Path(__file__).parents[3] / "support" / "normalized_log_v1.json"
    legacy = canonical_adapter.validate_json(legacy_path.read_text())
    assert legacy.kind == "normalized"
    legacy_batch = LogWriteBatch(records=(project_analytics_log(legacy),))
    path = tmp_path / "analytics.sqlite3"
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        await runtime.create_writer().append_logs(legacy_batch)
        async with runtime.connection() as connection:
            async with connection.execute("SELECT normalization_json FROM analytics_logs") as cursor:
                retained_legacy = (await cursor.fetchone())[0]
    finally:
        await runtime.shutdown()
    usage_payload = _producer_payload("codex_response_usage.json")
    _with_attribute(usage_payload, "input_token_count", {"stringValue": "9007199254741000"})
    _with_attribute(usage_payload, "cached_token_count", {"intValue": "9007199254740993"})
    _with_attribute(usage_payload, "tool_token_count", {"stringValue": "9007199254741200"})
    usage = normalize_analytics_logs(usage_payload, datetime(2026, 1, 1, tzinfo=timezone.utc))
    reopened = SqliteAnalyticsRuntime(path, ())
    try:
        await reopened.create_writer().append_logs(usage)
        async with reopened.connection() as connection:
            async with connection.execute("SELECT normalization_json, activity_kind, outcome FROM analytics_logs ORDER BY rowid") as cursor:
                stored = await cursor.fetchall()
    finally:
        await reopened.shutdown()
    assert stored[0][0] == retained_legacy
    assert canonical_adapter.validate_json(stored[0][0]) == legacy
    assert canonical_adapter.validate_json(stored[1][0]) == usage.records[0].normalization
    assert "9007199254740993" in stored[1][0]
    assert [(row[1], row[2]) for row in stored] == [(None, None), (None, None)]


@pytest.mark.asyncio
async def test_reported_decimal_cost_survives_restart_without_float_rounding(tmp_path: Path) -> None:
    payload = _producer_payload("claude_model_request.json")
    _with_attribute(payload, "cost_usd", {"stringValue": "0.123456789012345678"})
    record = cast(dict[str, JsonValue], payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0])
    record["attributes"] = [attribute for attribute in cast(list[dict[str, JsonValue]], record["attributes"]) if attribute["key"] != "cost_usd_micros"]
    batch = normalize_analytics_logs(payload, datetime(2026, 1, 1, tzinfo=timezone.utc))
    path = tmp_path / "analytics.sqlite3"
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        await runtime.create_writer().append_logs(batch)
    finally:
        await runtime.shutdown()
    reopened = SqliteAnalyticsRuntime(path, ())
    try:
        async with reopened.connection() as connection:
            async with connection.execute("SELECT normalization_json FROM analytics_logs") as cursor:
                stored = (await cursor.fetchone())[0]
    finally:
        await reopened.shutdown()
    assert "0.123456789012345678" in stored
    assert TypeAdapter(NormalizationEvidence).validate_json(stored) == batch.records[0].normalization
