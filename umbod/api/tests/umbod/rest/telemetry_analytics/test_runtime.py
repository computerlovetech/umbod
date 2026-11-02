from pathlib import Path

from fastapi.testclient import TestClient

from umbod.config import AppConfig, OtlpReceiverConfig, TelemetryAnalyticsConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.rest.main import create_app
from umbod.rest.telemetry.dependencies import get_telemetry_sink

from .conftest import AnalyticsVerifier
from .test_routes import BASE


def test_disabled_runtime_reports_unavailability_not_zero(
    configuration: AppConfig, query_body: dict[str, object],
) -> None:
    root = create_app(configuration, (), admin_verifier=AnalyticsVerifier())
    with TestClient(root, headers={"Authorization": "Bearer admin"}) as client:
        response = client.post(BASE, json=query_body)
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]
    assert response.headers["cache-control"] == "no-store"


class AcceptingTelemetrySink:
    def export(self, batch: TelemetryExport) -> None:
        return None


def test_mounted_admin_reader_queries_ingested_records_after_restart(
    configuration: AppConfig, query_body: dict[str, object], tmp_path: Path,
) -> None:
    settings = configuration.model_copy(update={
        "otlp_receiver": OtlpReceiverConfig(enabled=True, bearer_token="analytics-ingestion"),
        "telemetry_analytics": TelemetryAnalyticsConfig(enabled=True, sqlite_path=str(tmp_path / "analytics.sqlite3")),
    })
    payload = {"resourceLogs": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "codex"}}]},
        "scopeLogs": [{"logRecords": [{
            "timeUnixNano": "1767226200000000000", "severityText": "INFO", "eventName": "tool_result",
            "attributes": [{"key": "tool.name", "value": {"stringValue": "shell"}}],
        }, {
            "timeUnixNano": "1767226800000000000", "severityText": "ERROR", "eventName": "tool_result",
            "attributes": [{"key": "tool.name", "value": {"stringValue": "shell"}}],
        }]}],
    }]}
    root = create_app(settings, (), admin_verifier=AnalyticsVerifier())

    def provide_sink() -> TelemetrySink:
        return AcceptingTelemetrySink()

    root.dependency_overrides[get_telemetry_sink] = provide_sink
    with TestClient(root) as client:
        exported = client.post("/v1/logs", json=payload, headers={"Authorization": "Bearer analytics-ingestion"})
        assert exported.status_code == 200
    restarted = create_app(settings, (), admin_verifier=AnalyticsVerifier())
    with TestClient(restarted, headers={"Authorization": "Bearer admin"}) as client:
        response = client.post(BASE, json=query_body | {
            "filters": [{"dimension": "severity", "values": ["ERROR"]}],
            "group_by": ["source", "event_name", "tool_name"],
            "bucketing": {"kind": "fixed", "width": "hour"},
        })
    assert response.status_code == 200
    assert response.json() == {"rows": [{
        "groups": [
            {"dimension": "source", "value": {"kind": "present", "value": "codex"}},
            {"dimension": "event_name", "value": {"kind": "present", "value": "tool_result"}},
            {"dimension": "tool_name", "value": {"kind": "present", "value": "shell"}},
        ],
        "count": 1,
        "bucket": {"kind": "bucket", "start": "2026-01-01T00:00:00Z"},
    }]}
