import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.config import AppConfig, OtlpReceiverConfig, RestConfig, RuntimeConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import InstanceScope, LogCountQuery, NoTimeBuckets, TelemetryAnalyticsRuntime, TelemetryAnalyticsUnavailable, TimeRange
from umbod.rest.telemetry import application as telemetry_application
from umbod.rest.main import create_app
from umbod.rest.telemetry.application import create_telemetry_app
from umbod.rest.telemetry.dependencies import get_analytics_reader, get_telemetry_sink

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.telemetry_runtime import InMemoryTelemetryAnalyticsRuntime


@pytest.fixture(autouse=True)
def enabled_telemetry_logging() -> Iterator[None]:
    logger = logging.getLogger("umbod.structured")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


class AcceptedTelemetrySink:
    def __init__(self) -> None:
        self.exports: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        self.exports.append(batch)


def collector_settings() -> TelemetryAppConfig:
    return TelemetryAppConfig(
        runtime=RuntimeConfig(),
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="collector-test"),
        telemetry_analytics=TelemetryAnalyticsConfig(enabled=False),
    )


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_standalone_receiver_serves_only_collection_and_health(signal: str) -> None:
    with TestClient(create_telemetry_app(collector_settings())) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").status_code == 200
        assert client.post(f"/v1/{signal}", json={}, headers={"Authorization": "Bearer collector-test"}).status_code == 200
        assert client.post(f"/v1/{signal}", json={}).status_code == 401
        assert client.get("/api/admin/connectors").status_code == 404


def test_receiver_can_be_mounted_with_explicit_lifespan() -> None:
    collector = create_telemetry_app(collector_settings())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with collector.router.lifespan_context(collector):
            yield

    parent = FastAPI(lifespan=lifespan)
    parent.mount("/telemetry", collector)
    with TestClient(parent) as client:
        assert client.post("/telemetry/v1/logs", json={}, headers={"Authorization": "Bearer collector-test"}).status_code == 200


@pytest.mark.anyio
async def test_standalone_analytics_retains_records_across_application_reconstruction_and_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = collector_settings()
    query = LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=datetime(1970, 1, 1, tzinfo=timezone.utc),
            end=datetime(3000, 1, 1, tzinfo=timezone.utc),
        ),
        filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"), max_groups=10,
    )
    persistence = create_inmemory_runtime()
    selected_settings: list[AppConfig | TelemetryAppConfig] = []

    def select_runtime(config: AppConfig | TelemetryAppConfig) -> TelemetryAnalyticsRuntime:
        selected_settings.append(config)
        return InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness)

    sink = AcceptedTelemetrySink()

    def provide_sink() -> TelemetrySink:
        return sink

    try:
        monkeypatch.setattr(telemetry_application, "create_configured_analytics_runtime", select_runtime)
        app = create_telemetry_app(settings)
        app.dependency_overrides[get_telemetry_sink] = provide_sink
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://collector") as client:
                response = await client.post(
                    "/v1/logs",
                    json={"resourceLogs": [{"scopeLogs": [{"logRecords": [{"severityText": "INFO"}]}]}]},
                    headers={"Authorization": "Bearer collector-test"},
                )
                assert response.status_code == 200
                reader = app.dependency_overrides[get_analytics_reader]()
                assert (await reader.count_logs(query)).rows[0].count == 1
                assert len(sink.exports) == 1
        recreated = create_telemetry_app(settings)
        async with recreated.router.lifespan_context(recreated):
            with pytest.raises(TelemetryAnalyticsUnavailable):
                await reader.count_logs(query)
            recreated_reader = recreated.dependency_overrides[get_analytics_reader]()
            assert (await recreated_reader.count_logs(query)).rows[0].count == 1
            assert recreated_reader is not reader
        assert len(selected_settings) == 2
        assert all(config is settings for config in selected_settings)
    finally:
        await persistence.shutdown()


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_api_never_includes_ingestion(
    signal: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        connector_store={"type": "inmemory"},
        telemetry_analytics=TelemetryAnalyticsConfig(enabled=False),
        rest=RestConfig(metrics_enabled=False),
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="collector-test"),
    )
    app = create_app(settings=settings, connector_registrations=())
    with TestClient(app) as client:
        response = client.post(
            f"/v1/{signal}", json={},
            headers={"Authorization": "Bearer collector-test"},
        )
        assert response.status_code == 404
        assert client.post(f"/v1/{signal}", json={}).status_code == 404
