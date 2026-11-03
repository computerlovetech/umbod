from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from umbod.config import AppConfig, OtlpReceiverConfig, RestConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    LogDimension,
    LogWriteBatch,
    NoTimeBuckets,
    OwnersScope,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
    TimeRange,
)
from umbod.infrastructure import create_configured_analytics_runtime
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.main import create_app_with_shared_metrics
from umbod.rest.metrics import PrometheusRestMetricsRecorder
from umbod.rest.metrics.http_server import create_rest_metrics_app
from umbod.rest.telemetry.application import create_receiver_app_with_registry
from umbod.rest.telemetry.dependencies import get_analytics_writer, get_telemetry_sink

BASE = "/api/admin/telemetry/log-counts"
pytestmark = pytest.mark.anyio


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        self.batches.append(batch)


class AdminVerifier:
    def verify(self, token: str) -> JwtClaims:
        if token != "admin":
            raise JwtVerificationError("Invalid test credentials")
        return JwtClaims(claims={
            "iss": "test:analytics", "sub": "admin", "groups": ["analytics-admins"],
        })


class RecordingRuntime:
    def __init__(self, delegate: TelemetryAnalyticsRuntime) -> None:
        self.delegate = delegate
        self.ready_calls = 0
        self.shutdown_calls = 0

    async def ensure_ready(self) -> None:
        self.ready_calls += 1
        await self.delegate.ensure_ready()

    async def shutdown(self) -> None:
        self.shutdown_calls += 1
        await self.delegate.shutdown()

    def create_reader(self) -> TelemetryAnalyticsReader:
        return self.delegate.create_reader()

    def create_writer(self) -> TelemetryAnalyticsWriter:
        return self.delegate.create_writer()


class UnavailableWriter:
    async def append_logs(self, batch: LogWriteBatch) -> None:
        raise TelemetryAnalyticsUnavailable("private database diagnostic")


@dataclass(frozen=True)
class Applications:
    api: AsyncClient
    collector: AsyncClient
    collector_app: FastAPI
    runtime: RecordingRuntime
    sink: RecordingSink
    metrics: PrometheusRestMetricsRecorder


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="analytics-ingestion"),
        telemetry_analytics=TelemetryAnalyticsConfig(
            enabled=True, sqlite_path=str(tmp_path / "analytics.sqlite3"),
        ),
        admin_authentication={
            "mode": "jwt", "environment": "development", "required_membership": "analytics-admins",
        },
        rest=RestConfig(metrics_enabled=False),
    )


@asynccontextmanager
async def _applications(configuration: AppConfig) -> AsyncIterator[Applications]:
    runtime = RecordingRuntime(create_configured_analytics_runtime(configuration))
    sink = RecordingSink()
    metrics = PrometheusRestMetricsRecorder()

    def provide_sink() -> TelemetrySink:
        return sink

    async with AsyncExitStack() as stack:
        stack.push_async_callback(runtime.shutdown)
        await runtime.ensure_ready()
        api = create_app_with_shared_metrics(
            runtime, metrics, settings=configuration, connector_registrations=(), admin_verifier=AdminVerifier(),
        )
        collector = create_receiver_app_with_registry(TelemetryAppConfig(
            runtime=configuration.runtime,
            otlp_receiver=configuration.otlp_receiver,
            telemetry_analytics=configuration.telemetry_analytics,
        ), runtime, metrics.registry)
        collector.dependency_overrides[get_telemetry_sink] = provide_sink
        await stack.enter_async_context(api.router.lifespan_context(api))
        await stack.enter_async_context(collector.router.lifespan_context(collector))
        api_client = await stack.enter_async_context(AsyncClient(
            transport=ASGITransport(app=api), base_url="http://api",
            headers={"Authorization": "Bearer admin"},
        ))
        collector_client = await stack.enter_async_context(AsyncClient(
            transport=ASGITransport(app=collector), base_url="http://collector",
            headers={"Authorization": "Bearer analytics-ingestion"},
        ))
        yield Applications(api_client, collector_client, collector, runtime, sink, metrics)


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


def _query_body(query: LogCountQuery) -> dict[str, object]:
    return query.model_dump(mode="json", exclude={"scope"})


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


async def test_accepted_logs_are_queryable_through_admin_api_and_persist_after_restart(
    configuration: AppConfig, query: LogCountQuery,
) -> None:
    async with _applications(configuration) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        count = await apps.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 1
    async with _applications(configuration) as restarted:
        count = await restarted.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 1


async def test_collector_and_rest_metrics_share_existing_exposition(
    configuration: AppConfig, query: LogCountQuery,
) -> None:
    async with _applications(configuration) as apps:
        assert (await apps.collector.post("/v1/logs", json=_payload())).status_code == 200
        assert (await apps.api.post(BASE, json=_query_body(query))).status_code == 200
        async with AsyncClient(
            transport=ASGITransport(app=create_rest_metrics_app(apps.metrics)), base_url="http://metrics",
        ) as metrics_client:
            response = await metrics_client.get("/metrics")
        assert response.status_code == 200
        assert 'umbod_rest_requests_total{method="POST",route="/admin/telemetry/log-counts",status_class="2xx"} 1.0' in response.text
        assert 'umbod_collector_requests_total{method="POST",route="/v1/logs",status_class="2xx"} 1.0' in response.text
        assert "umbod_collector_log_records_accepted_total 1.0" in response.text


async def test_shared_runtime_lifetime_is_owned_only_by_host(configuration: AppConfig) -> None:
    async with _applications(configuration) as apps:
        assert apps.runtime.ready_calls == 1
        assert apps.runtime.shutdown_calls == 0
        reader = apps.runtime.create_reader()
    assert apps.runtime.ready_calls == 1
    assert apps.runtime.shutdown_calls == 1
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await reader.count_logs(LogCountQuery(
            scope=InstanceScope(kind="instance"),
            time_range=TimeRange(
                start=datetime(1970, 1, 1, tzinfo=timezone.utc),
                end=datetime(3000, 1, 1, tzinfo=timezone.utc),
            ),
            filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"), max_groups=10,
        ))


async def test_shared_ingestion_identity_does_not_create_trusted_owner(
    configuration: AppConfig, query: LogCountQuery,
) -> None:
    owner_query = query.model_copy(update={"scope": OwnersScope(kind="owners", owner_ids=("claimed-owner",))})
    async with _applications(configuration) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        result = await apps.runtime.create_reader().count_logs(owner_query)
        assert result.rows[0].count == 0


@pytest.mark.parametrize("authorized,valid,status", [(False, True, 401), (True, False, 400)])
async def test_rejected_exports_do_not_write_analytics(
    configuration: AppConfig, query: LogCountQuery, authorized: bool, valid: bool, status: int,
) -> None:
    async with _applications(configuration) as apps:
        response = await apps.collector.post(
            "/v1/logs", json=_payload() if valid else {"resourceLogs": "invalid"},
            headers={"Authorization": "Bearer analytics-ingestion" if authorized else "Bearer invalid"},
        )
        assert response.status_code == status
        count = await apps.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 0
        assert apps.sink.batches == []


async def test_analytics_failure_is_not_acknowledged_and_hides_backend_details(
    configuration: AppConfig, query: LogCountQuery,
) -> None:
    def unavailable_writer() -> TelemetryAnalyticsWriter:
        return UnavailableWriter()

    async with _applications(configuration) as apps:
        apps.collector_app.dependency_overrides[get_analytics_writer] = unavailable_writer
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 503
        assert response.json() == {"code": 14, "message": "Telemetry analytics is unavailable"}
        count = await apps.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 0


async def test_analytics_groups_match_normalized_export_attributes(
    configuration: AppConfig, query: LogCountQuery,
) -> None:
    grouped = query.model_copy(update={"group_by": (LogDimension.SOURCE, LogDimension.EVENT_NAME, LogDimension.TOOL_NAME)})
    async with _applications(configuration) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        result = await apps.api.post(BASE, json=_query_body(grouped))
        assert result.status_code == 200
        assert tuple(group["value"]["value"] for group in result.json()["rows"][0]["groups"]) == ("codex", "tool_result", "shell")


@pytest.mark.parametrize("source,count", [("codex", 1), ("other", 0)])
async def test_admin_filters_match_collector_logs(
    configuration: AppConfig, query: LogCountQuery, source: str, count: int,
) -> None:
    async with _applications(configuration) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        result = await apps.api.post(BASE, json=_query_body(query) | {
            "filters": [{"dimension": "source", "values": [source]}],
        })
        assert result.status_code == 200
        assert result.json()["rows"][0]["count"] == count


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
async def test_listener_boundaries_and_admin_authentication_remain_separate(
    configuration: AppConfig, query: LogCountQuery, signal: str,
) -> None:
    async with _applications(configuration) as apps:
        for token in ("analytics-ingestion", "invalid"):
            headers = {"Authorization": f"Bearer {token}"}
            assert (await apps.api.post(f"/v1/{signal}", json={}, headers=headers)).status_code == 404
        assert (await apps.collector.post(
            f"/v1/{signal}", json={}, headers={"Authorization": "Bearer invalid"},
        )).status_code == 401
        assert (await apps.collector.post(BASE, json=_query_body(query))).status_code == 404
        assert (await apps.api.post(
            BASE, json=_query_body(query), headers={"Authorization": "Bearer invalid"},
        )).status_code == 401
        assert (await apps.api.post(
            BASE, json=_query_body(query), headers={"Authorization": "Bearer analytics-ingestion"},
        )).status_code == 401
