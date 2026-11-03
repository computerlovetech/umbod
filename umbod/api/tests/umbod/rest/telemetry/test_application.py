import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.config import AppConfig, OtlpReceiverConfig, RestConfig, RuntimeConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import InstanceScope, LogCountQuery, NoTimeBuckets, TelemetryAnalyticsUnavailable, TimeRange
from umbod.rest.main import create_app
from umbod.rest.telemetry.application import create_telemetry_app
from umbod.rest.telemetry.dependencies import get_analytics_reader, get_telemetry_sink


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
    def export(self, batch: TelemetryExport) -> None:
        return None


def collector_settings() -> TelemetryAppConfig:
    return TelemetryAppConfig(
        runtime=RuntimeConfig(),
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="collector-test"),
        telemetry_analytics=TelemetryAnalyticsConfig(),
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


def test_standalone_analytics_persists_and_shuts_down(tmp_path: Path) -> None:
    settings = collector_settings()
    settings.telemetry_analytics = TelemetryAnalyticsConfig(
        enabled=True, sqlite_path=str(tmp_path / "collector.sqlite3"),
    )
    query = LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=datetime(1970, 1, 1, tzinfo=timezone.utc),
            end=datetime(3000, 1, 1, tzinfo=timezone.utc),
        ),
        filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"), max_groups=10,
    )
    app = create_telemetry_app(settings)

    def provide_sink() -> TelemetrySink:
        return AcceptedTelemetrySink()

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    with TestClient(app) as client:
        response = client.post(
            "/v1/logs",
            json={"resourceLogs": [{"scopeLogs": [{"logRecords": [{"severityText": "INFO"}]}]}]},
            headers={"Authorization": "Bearer collector-test"},
        )
        assert response.status_code == 200
        reader = app.dependency_overrides[get_analytics_reader]()
        assert client.portal.call(reader.count_logs, query).rows[0].count == 1
    restarted = create_telemetry_app(settings)
    with TestClient(restarted) as client:
        with pytest.raises(TelemetryAnalyticsUnavailable):
            client.portal.call(reader.count_logs, query)
        restarted_reader = restarted.dependency_overrides[get_analytics_reader]()
        assert client.portal.call(restarted_reader.count_logs, query).rows[0].count == 1


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_api_never_includes_ingestion(
    signal: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
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
