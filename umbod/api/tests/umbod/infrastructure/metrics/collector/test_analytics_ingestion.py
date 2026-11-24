import json
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from umbod.config import AppConfig, OtlpReceiverConfig, RestConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    LogDimension,
    LogAppendBatch,
    NoTimeBuckets,
    OwnersScope,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
    TimeRange,
    analytics_owner_id,
)
from tests.persistence_runtime import create_inmemory_runtime
from tests.support.telemetry_runtime import InMemoryTelemetryAnalyticsRuntime
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.authentication.verifiers import ProductionJwksJwtVerifier
from umbod.rest.main import create_app_with_shared_persistence
from umbod.infrastructure.metrics.rest import PrometheusRestMetricsRecorder
from umbod.infrastructure.metrics.rest import create_rest_metrics_app
from umbod.infrastructure.metrics.collector import create_receiver_app_with_registry
from umbod.rest.telemetry.dependencies import get_analytics_writer, get_telemetry_sink
from umbod.rest.telemetry.token_authentication import install_telemetry_token_verifier

BASE = "/api/admin/telemetry/log-counts"
PERSONAL = "/api/me/telemetry/log-counts"
ISSUER = "https://identity.example.test/"
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


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _user_verifier(signing_key: rsa.RSAPrivateKey) -> ProductionJwksJwtVerifier:
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    key["kid"] = "analytics-user-key"
    verifier = ProductionJwksJwtVerifier(ISSUER + "jwks", ISSUER, "api")
    cache = verifier.jwks_client.jwk_set_cache
    assert cache is not None
    cache.put({"keys": [key]})
    return verifier


def _user_login(signing_key: rsa.RSAPrivateKey, subject: str) -> dict[str, str]:
    token = jwt.encode(
        {"iss": ISSUER, "aud": "api", "sub": subject,
         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        signing_key, algorithm="RS256", headers={"kid": "analytics-user-key"},
    )
    return {"Authorization": f"Bearer {token}"}


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
    async def append_logs(self, batch: LogAppendBatch) -> None:
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
        connector_store={"type": "inmemory"},
        telemetry_analytics=TelemetryAnalyticsConfig(enabled=False),
        admin_authentication={
            "mode": "jwt", "environment": "development", "required_membership": "analytics-admins",
        },
        rest=RestConfig(metrics_enabled=False),
    )


@pytest.fixture
async def analytics_persistence() -> AsyncIterator[PersistenceRuntime]:
    persistence = create_inmemory_runtime()
    try:
        yield persistence
    finally:
        await persistence.shutdown()


@asynccontextmanager
async def _applications(
    configuration: AppConfig, persistence: PersistenceRuntime,
    user_verifier: ProductionJwksJwtVerifier | None,
) -> AsyncIterator[Applications]:
    runtime = RecordingRuntime(InMemoryTelemetryAnalyticsRuntime(persistence.database, persistence.readiness))
    sink = RecordingSink()
    metrics = PrometheusRestMetricsRecorder()

    def provide_sink() -> TelemetrySink:
        return sink

    async with AsyncExitStack() as stack:
        stack.push_async_callback(runtime.shutdown)
        await runtime.ensure_ready()
        api = create_app_with_shared_persistence(
            persistence, runtime, metrics, settings=configuration, connector_registrations=(),
            admin_verifier=AdminVerifier(), user_verifier=user_verifier,
        )
        collector = create_receiver_app_with_registry(TelemetryAppConfig(
            runtime=configuration.runtime,
            otlp_receiver=configuration.otlp_receiver,
            telemetry_analytics=configuration.telemetry_analytics,
        ), runtime, metrics.registry)
        install_telemetry_token_verifier(collector, persistence, configuration)
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
        filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"), pagination={"limit": 100, "offset": 0},
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


async def test_accepted_logs_are_queryable_across_application_reconstruction(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
) -> None:
    async with _applications(configuration, analytics_persistence, None) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        count = await apps.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 1
    async with _applications(configuration, analytics_persistence, None) as recreated:
        count = await recreated.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 1


async def test_collector_and_rest_metrics_share_existing_exposition(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
) -> None:
    async with _applications(configuration, analytics_persistence, None) as apps:
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


async def test_shared_runtime_lifetime_is_owned_only_by_host(configuration: AppConfig, analytics_persistence: PersistenceRuntime) -> None:
    async with _applications(configuration, analytics_persistence, None) as apps:
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
            filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"), pagination={"limit": 10, "offset": 0},
        ))


@pytest.mark.parametrize("allow_unauthenticated", [False, True])
async def test_shared_and_unauthenticated_ingestion_do_not_create_trusted_owners(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
    allow_unauthenticated: bool,
) -> None:
    owner_ids = ("claimed-owner", analytics_owner_id(ISSUER, "claimed-owner"))
    owner_query = query.model_copy(update={"scope": OwnersScope(kind="owners", owner_ids=owner_ids)})
    receiver = configuration.otlp_receiver.model_copy(update={"allow_unauthenticated": allow_unauthenticated})
    settings = configuration.model_copy(update={"otlp_receiver": receiver})
    async with _applications(settings, analytics_persistence, None) as apps:
        if allow_unauthenticated:
            del apps.collector.headers["Authorization"]
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        result = await apps.runtime.create_reader().count_logs(owner_query)
        assert result.rows[0].count == 0


async def _export_owned_logs(apps: Applications, login: dict[str, str], count: int) -> None:
    created = await apps.api.post(
        "/api/me/personal-access-tokens",
        headers=login,
        json={
            "name": "Collector",
            "permissions": {"telemetry": "write"},
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    created.raise_for_status()
    headers = {"Authorization": "Bearer " + created.json()["token"]}
    for _ in range(count):
        (await apps.collector.post("/v1/logs", json=_payload(), headers=headers)).raise_for_status()


async def test_personal_counts_separate_token_owners_and_exclude_unowned_logs(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    alice = _user_login(signing_key, "alice")
    claimed_owner = _user_login(signing_key, "claimed-owner")
    async with _applications(configuration, analytics_persistence, _user_verifier(signing_key)) as apps:
        await _export_owned_logs(apps, alice, 1)
        await _export_owned_logs(apps, claimed_owner, 2)
        (await apps.collector.post("/v1/logs", json=_payload())).raise_for_status()

        counts = []
        for path, headers in ((PERSONAL, alice), (PERSONAL, claimed_owner), (BASE, {})):
            response = await apps.api.post(path, json=_query_body(query), headers=headers)
            response.raise_for_status()
            counts.append(response.json()["rows"][0]["count"])
        assert counts == [1, 2, 4]


async def test_personal_count_requires_a_signed_in_caller(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    async with _applications(configuration, analytics_persistence, _user_verifier(signing_key)) as apps:
        del apps.api.headers["Authorization"]
        response = await apps.api.post(PERSONAL, json=_query_body(query))
        assert response.status_code == 401


@pytest.mark.parametrize("patch", [
    {"scope": {"kind": "instance"}},
    {"scope": {"kind": "owners", "owner_ids": ["other"]}},
    {"owner_id": "other"},
    {"pagination": {"limit": "100", "offset": 0}},
])
async def test_personal_count_rejects_scope_and_invalid_count_queries(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
    signing_key: rsa.RSAPrivateKey, patch: dict[str, object],
) -> None:
    async with _applications(configuration, analytics_persistence, _user_verifier(signing_key)) as apps:
        response = await apps.api.post(
            PERSONAL, json=_query_body(query) | patch, headers=_user_login(signing_key, "alice"),
        )
        assert response.status_code == 422


async def test_personal_count_returns_uncacheable_503_when_reader_is_unavailable(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    async with _applications(configuration, analytics_persistence, _user_verifier(signing_key)) as apps:
        await apps.runtime.shutdown()
        response = await apps.api.post(PERSONAL, json=_query_body(query), headers=_user_login(signing_key, "alice"))
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert "rows" not in response.json()


@pytest.mark.parametrize("authorized,valid,status", [(False, True, 401), (True, False, 400)])
async def test_rejected_exports_do_not_write_analytics(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery, authorized: bool, valid: bool, status: int,
) -> None:
    async with _applications(configuration, analytics_persistence, None) as apps:
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
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
) -> None:
    def unavailable_writer() -> TelemetryAnalyticsWriter:
        return UnavailableWriter()

    async with _applications(configuration, analytics_persistence, None) as apps:
        apps.collector_app.dependency_overrides[get_analytics_writer] = unavailable_writer
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 503
        assert response.json() == {"code": 14, "message": "Telemetry analytics is unavailable"}
        count = await apps.api.post(BASE, json=_query_body(query))
        assert count.status_code == 200
        assert count.json()["rows"][0]["count"] == 0


async def test_analytics_groups_match_normalized_export_attributes(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery,
) -> None:
    grouped = query.model_copy(update={"group_by": (LogDimension.SOURCE, LogDimension.EVENT_NAME, LogDimension.TOOL_NAME)})
    async with _applications(configuration, analytics_persistence, None) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        result = await apps.api.post(BASE, json=_query_body(grouped))
        assert result.status_code == 200
        assert tuple(group["value"]["value"] for group in result.json()["rows"][0]["groups"]) == ("codex", "tool_result", "shell")


@pytest.mark.parametrize("source,count", [("codex", 1), ("other", 0)])
async def test_admin_filters_match_collector_logs(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery, source: str, count: int,
) -> None:
    async with _applications(configuration, analytics_persistence, None) as apps:
        response = await apps.collector.post("/v1/logs", json=_payload())
        assert response.status_code == 200
        result = await apps.api.post(BASE, json=_query_body(query) | {
            "filters": [{"dimension": "source", "values": [source]}],
        })
        assert result.status_code == 200
        assert result.json()["rows"][0]["count"] == count


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
async def test_listener_boundaries_and_admin_authentication_remain_separate(
    configuration: AppConfig, analytics_persistence: PersistenceRuntime, query: LogCountQuery, signal: str,
) -> None:
    async with _applications(configuration, analytics_persistence, None) as apps:
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
