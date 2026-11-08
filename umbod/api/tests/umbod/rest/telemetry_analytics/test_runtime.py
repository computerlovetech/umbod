import httpx
import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig, OtlpReceiverConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry.analytics import TelemetryAnalyticsRuntime, TelemetryAnalyticsUnavailable
from umbod.rest import main as rest_application
from umbod.rest.telemetry import application as telemetry_application
from umbod.rest.telemetry.application import create_telemetry_app
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.rest.main import create_app
from umbod.rest.telemetry.dependencies import get_telemetry_sink

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.telemetry_runtime import InMemoryTelemetryAnalyticsRuntime

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


class RecordingTelemetrySink:
    def __init__(self) -> None:
        self.batches: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        self.batches.append(batch)


@pytest.mark.anyio
async def test_admin_reader_queries_private_collector_records_after_application_reconstruction(
    configuration: AppConfig, query_body: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppConfig.model_validate(configuration.model_dump() | {
        "connector_store": {"type": "inmemory"},
        "otlp_receiver": OtlpReceiverConfig(enabled=True, bearer_token="analytics-ingestion"),
        "telemetry_analytics": TelemetryAnalyticsConfig(enabled=False),
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
    collector_settings = TelemetryAppConfig(
        runtime=settings.runtime,
        otlp_receiver=settings.otlp_receiver,
        telemetry_analytics=settings.telemetry_analytics,
    )
    persistence = create_inmemory_runtime()
    selected_settings: list[AppConfig | TelemetryAppConfig] = []
    runtimes: list[TelemetryAnalyticsRuntime] = []

    def select_runtime(config: AppConfig | TelemetryAppConfig) -> TelemetryAnalyticsRuntime:
        selected_settings.append(config)
        runtime = InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)
        runtimes.append(runtime)
        return runtime

    sink = RecordingTelemetrySink()

    def provide_sink() -> TelemetrySink:
        return sink

    try:
        monkeypatch.setattr(telemetry_application, "create_configured_analytics_runtime", select_runtime)
        monkeypatch.setattr(rest_application, "create_configured_analytics_runtime", select_runtime)
        collector = create_telemetry_app(collector_settings)
        collector.dependency_overrides[get_telemetry_sink] = provide_sink
        async with collector.router.lifespan_context(collector):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=collector), base_url="http://collector") as client:
                exported = await client.post("/v1/logs", json=payload, headers={"Authorization": "Bearer analytics-ingestion"})
                assert exported.status_code == 200
                assert len(sink.batches) == 1
                assert sink.batches[0].item_count == 2
        assert len(runtimes) == 1
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtimes[0].ensure_ready()
        recreated = create_app(settings, (), admin_verifier=AnalyticsVerifier())
        async with recreated.router.lifespan_context(recreated):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=recreated), base_url="http://api",
                headers={"Authorization": "Bearer admin"},
            ) as client:
                response = await client.post(BASE, json=query_body | {
                    "filters": [{"dimension": "severity", "values": ["ERROR"]}],
                    "group_by": ["source", "event_name", "tool_name"],
                    "bucketing": {"kind": "fixed", "width": "hour"},
                })
        assert len(runtimes) == 2
        assert runtimes[0] is not runtimes[1]
        assert selected_settings[0] is collector_settings
        assert selected_settings[1] is settings
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtimes[1].ensure_ready()
    finally:
        await persistence.shutdown()
    assert response.status_code == 200
    assert response.json() == {"has_more": False, "rows": [{
        "groups": [
            {"dimension": "source", "value": {"kind": "present", "value": "codex"}},
            {"dimension": "event_name", "value": {"kind": "present", "value": "tool_result"}},
            {"dimension": "tool_name", "value": {"kind": "present", "value": "shell"}},
        ],
        "count": 1,
        "bucket": {"kind": "bucket", "start": "2026-01-01T00:00:00Z"},
    }]}
