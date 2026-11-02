from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.config import AppConfig, OtlpReceiverConfig, RestConfig, TelemetryAnalyticsConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    LogCountResult,
    LogDimension,
    LogWriteBatch,
    NoTimeBuckets,
    OwnersScope,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
    TimeRange,
)
from umbod.rest.main import create_app
from umbod.rest.telemetry.dependencies import get_analytics_reader, get_analytics_writer, get_telemetry_sink


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        self.batches.append(batch)


class UnavailableWriter:
    async def append_logs(self, batch: LogWriteBatch) -> None:
        raise TelemetryAnalyticsUnavailable("private database diagnostic")


@pytest.fixture
def configuration(tmp_path: Path) -> AppConfig:
    return AppConfig(
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="analytics-ingestion"),
        telemetry_analytics=TelemetryAnalyticsConfig(
            enabled=True, sqlite_path=str(tmp_path / "analytics.sqlite3"),
        ),
        rest=RestConfig(metrics_enabled=False),
    )


@pytest.fixture
def app(configuration: AppConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    application = create_app(settings=configuration, connector_registrations=())
    sink = RecordingSink()

    def provide_sink() -> TelemetrySink:
        return sink

    application.dependency_overrides[get_telemetry_sink] = provide_sink
    return application


@pytest.fixture
def query() -> LogCountQuery:
    return LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=datetime(1970, 1, 1, tzinfo=timezone.utc),
            end=datetime(3000, 1, 1, tzinfo=timezone.utc),
        ),
        filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"), max_groups=100,
    )


def _reader(app: FastAPI) -> TelemetryAnalyticsReader:
    return app.dependency_overrides[get_analytics_reader]()


def _count(client: TestClient, reader: TelemetryAnalyticsReader, query: LogCountQuery) -> LogCountResult:
    return client.portal.call(reader.count_logs, query)


def _payload() -> dict[str, object]:
    return {"resourceLogs": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "codex"}}]},
        "scopeLogs": [{"logRecords": [{
            "timeUnixNano": "18446744073709551615",
            "severityText": "ERROR",
            "attributes": [
                {"key": "event.name", "value": {"stringValue": "tool_result"}},
                {"key": "tool.name", "value": {"stringValue": "shell"}},
                {"key": "enduser.id", "value": {"stringValue": "claimed-owner"}},
            ],
        }]}],
    }]}


def test_accepted_logs_are_queryable_and_persist_after_restart(
    app: FastAPI, configuration: AppConfig, query: LogCountQuery,
) -> None:
    with TestClient(app) as client:
        response = client.post("/v1/logs", json=_payload(), headers={"Authorization": "Bearer analytics-ingestion"})
        assert response.status_code == 200
        assert _count(client, _reader(app), query).rows[0].count == 1
    restarted = create_app(settings=configuration, connector_registrations=())
    with TestClient(restarted) as client:
        assert _count(client, _reader(restarted), query).rows[0].count == 1


def test_shared_ingestion_identity_does_not_create_trusted_owner(
    app: FastAPI, query: LogCountQuery,
) -> None:
    owner_query = LogCountQuery.model_validate(query.model_dump() | {
        "scope": OwnersScope(kind="owners", owner_ids=("claimed-owner",)),
    })
    with TestClient(app) as client:
        response = client.post("/v1/logs", json=_payload(), headers={"Authorization": "Bearer analytics-ingestion"})
        assert response.status_code == 200
        assert _count(client, _reader(app), owner_query).rows[0].count == 0


@pytest.mark.parametrize("authorized,valid", [(False, True), (True, False)])
def test_rejected_exports_do_not_write_analytics(
    app: FastAPI, query: LogCountQuery, authorized: bool, valid: bool,
) -> None:
    payload = _payload() if valid else {"resourceLogs": "invalid"}
    with TestClient(app) as client:
        response = client.post("/v1/logs", json=payload, headers={
            "Authorization": "Bearer analytics-ingestion" if authorized else "Bearer invalid",
        })
        assert response.status_code in (400, 401)
        assert _count(client, _reader(app), query).rows[0].count == 0


def test_analytics_failure_is_not_acknowledged_and_hides_backend_details(app: FastAPI) -> None:
    def unavailable_writer() -> TelemetryAnalyticsWriter:
        return UnavailableWriter()

    app.dependency_overrides[get_analytics_writer] = unavailable_writer
    with TestClient(app) as client:
        response = client.post("/v1/logs", json=_payload(), headers={"Authorization": "Bearer analytics-ingestion"})
        assert response.status_code == 503
        assert response.json() == {"code": 14, "message": "Telemetry analytics is unavailable"}


def test_analytics_groups_match_normalized_export_attributes(app: FastAPI, query: LogCountQuery) -> None:
    grouped = LogCountQuery.model_validate(query.model_dump() | {
        "group_by": (LogDimension.SOURCE, LogDimension.EVENT_NAME, LogDimension.TOOL_NAME),
    })
    with TestClient(app) as client:
        client.post("/v1/logs", json=_payload(), headers={"Authorization": "Bearer analytics-ingestion"})
        result = _count(client, _reader(app), grouped)
        assert tuple(group.value.value for group in result.rows[0].groups) == ("codex", "tool_result", "shell")
