from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest

from umbod.config import AppConfig, OtlpReceiverConfig, RuntimeConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.diagnostics import ApplicationFailure, PublishingSignalFailureHandler
from umbod.core.signals import Signal
from umbod.core.telemetry import TelemetryExport, TelemetrySink, TelemetryUnavailable
from umbod.core.telemetry.analytics import LogWriteBatch, TelemetryAnalyticsUnavailable, TelemetryAnalyticsWriter
from umbod.logging import create_application_failure_signal
from umbod.rest.metrics import PrometheusRestMetricsRecorder
from umbod.rest.metrics.http_server import create_rest_metrics_app
from umbod.rest.metrics.models import CompletedRestRequest
from umbod.rest.telemetry.application import create_telemetry_app
from umbod.rest.telemetry.composition import install_telemetry_receiver_with_registry
from umbod.rest.telemetry.metrics import PrometheusCollectorMetrics
from umbod.rest.telemetry.dependencies import get_analytics_writer, get_telemetry_sink
from umbod.rest.telemetry.observations import AcceptedCollectorLogs, CompletedCollectorRequest, get_accepted_logs_publisher


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[TelemetryExport] = []
        self.unavailable = False

    def export(self, batch: TelemetryExport) -> None:
        if self.unavailable:
            raise TelemetryUnavailable("private sink sentinel")
        self.batches.append(batch)


class RecordingWriter:
    def __init__(self) -> None:
        self.batches: list[LogWriteBatch] = []
        self.unavailable = False

    async def append_logs(self, batch: LogWriteBatch) -> None:
        if self.unavailable:
            raise TelemetryAnalyticsUnavailable("private analytics sentinel")
        self.batches.append(batch)


@dataclass(frozen=True)
class Collector:
    client: TestClient
    metrics: PrometheusRestMetricsRecorder
    sink: RecordingSink
    writer: RecordingWriter
    accepted: Signal[AcceptedCollectorLogs]


@pytest.fixture
def collector() -> Collector:
    metrics = PrometheusRestMetricsRecorder()
    sink = RecordingSink()
    writer = RecordingWriter()
    app = FastAPI()
    install_telemetry_receiver_with_registry(app, AppConfig(otlp_receiver=OtlpReceiverConfig(
        enabled=True, bearer_token="credential-sentinel",
    )), metrics.registry)

    def provide_sink() -> TelemetrySink:
        return sink

    def provide_writer() -> TelemetryAnalyticsWriter:
        return writer

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    app.dependency_overrides[get_analytics_writer] = provide_writer
    accepted = app.dependency_overrides[get_accepted_logs_publisher]()
    return Collector(TestClient(app), metrics, sink, writer, accepted)


def _logs(count: int) -> ExportLogsServiceRequest:
    request = ExportLogsServiceRequest()
    for _ in range(2):
        scope = request.resource_logs.add().scope_logs.add()
        for _ in range(count):
            scope.log_records.add().body.string_value = "payload-sentinel"
    return request


@pytest.mark.parametrize("protobuf", [False, True])
@pytest.mark.parametrize("count", [0, 2])
def test_accepted_records_count_all_records_and_repeated_exports(
    collector: Collector, protobuf: bool, count: int,
) -> None:
    request = _logs(count)
    events: list[AcceptedCollectorLogs] = []
    collector.accepted.connect("test.observer", events.append)
    for _ in range(2):
        headers = {"Authorization": "Bearer credential-sentinel"}
        if protobuf:
            response = collector.client.post("/v1/logs", content=request.SerializeToString(), headers={
                **headers, "Content-Type": "application/x-protobuf",
            })
        else:
            response = collector.client.post("/v1/logs", json=MessageToDict(request), headers=headers)
        assert response.status_code == 200
    assert collector.metrics.registry.get_sample_value("umbod_collector_log_records_accepted_total") == count * 4
    assert events == [AcceptedCollectorLogs(count * 2)] * 2
    assert collector.metrics.registry.get_sample_value("umbod_collector_requests_total", {
        "method": "POST", "route": "/v1/logs", "status_class": "2xx",
    }) == 2
    assert collector.metrics.registry.get_sample_value("umbod_collector_request_duration_seconds_count", {
        "method": "POST", "route": "/v1/logs", "status_class": "2xx",
    }) == 2


@pytest.mark.parametrize("failure,status", [("auth", 401), ("validation", 400), ("analytics", 503), ("sink", 503)])
def test_failed_ingestion_counts_requests_but_not_accepted_logs(
    collector: Collector, failure: str, status: int,
) -> None:
    collector.writer.unavailable = failure == "analytics"
    collector.sink.unavailable = failure == "sink"
    response = collector.client.post(
        "/v1/logs", json={"resourceLogs": "invalid"} if failure == "validation" else MessageToDict(_logs(2)),
        headers={"Authorization": "Bearer invalid" if failure == "auth" else "Bearer credential-sentinel"},
    )
    assert response.status_code == status
    assert collector.metrics.registry.get_sample_value("umbod_collector_log_records_accepted_total") == 0
    labels = {"method": "POST", "route": "/v1/logs", "status_class": f"{status // 100}xx"}
    assert collector.metrics.registry.get_sample_value("umbod_collector_requests_total", labels) == 1
    assert collector.metrics.registry.get_sample_value("umbod_collector_request_duration_seconds_count", labels) == 1
    assert len(collector.sink.batches) == (1 if failure == "analytics" else 0)


@pytest.mark.parametrize("signal", ["metrics", "traces"])
def test_other_signals_do_not_increment_log_count(collector: Collector, signal: str) -> None:
    response = collector.client.post(f"/v1/{signal}", json={}, headers={"Authorization": "Bearer credential-sentinel"})
    assert response.status_code == 200
    assert collector.metrics.registry.get_sample_value("umbod_collector_log_records_accepted_total") == 0
    assert collector.metrics.registry.get_sample_value("umbod_collector_requests_total", {
        "method": "POST", "route": f"/v1/{signal}", "status_class": "2xx",
    }) == 1


def test_exposition_shares_rest_registry_and_excludes_unbounded_paths(collector: Collector) -> None:
    collector.metrics.record_completed_request(CompletedRestRequest(
        method="GET", normalized_route="/admin/connectors", status_class="2xx", duration_seconds=0.01,
    ))
    collector.client.post("/v1/logs?secret=query-sentinel", json={})
    for path in ("/ready", "/health", "/private-path-sentinel"):
        collector.client.get(path)
    response = TestClient(create_rest_metrics_app(collector.metrics)).get("/metrics")
    assert response.status_code == 200
    assert 'umbod_rest_requests_total{method="GET",route="/admin/connectors",status_class="2xx"} 1.0' in response.text
    assert 'umbod_collector_requests_total{method="POST",route="/v1/logs",status_class="4xx"} 1.0' in response.text
    for secret in ("query-sentinel", "private-path-sentinel", "credential-sentinel", "payload-sentinel", "/ready", "/health"):
        assert secret not in response.text


def test_observation_failure_does_not_change_ingestion_result(collector: Collector) -> None:
    observed: list[AcceptedCollectorLogs] = []

    def fail(event: AcceptedCollectorLogs) -> None:
        raise RuntimeError("private sentinel")

    collector.accepted.connect("test.failure", fail)
    collector.accepted.connect("test.observer", observed.append)
    response = collector.client.post("/v1/logs", json=MessageToDict(_logs(2)), headers={
        "Authorization": "Bearer credential-sentinel",
    })
    assert response.status_code == 200
    assert observed == [AcceptedCollectorLogs(4)]
    assert collector.metrics.registry.get_sample_value("umbod_collector_log_records_accepted_total") == 4


def test_application_observations_are_isolated(collector: Collector) -> None:
    other_metrics = PrometheusRestMetricsRecorder()
    other_app = FastAPI()
    install_telemetry_receiver_with_registry(other_app, AppConfig(), other_metrics.registry)
    collector.client.post("/v1/logs", json={})
    assert other_metrics.registry.get_sample_value("umbod_collector_log_records_accepted_total") == 0
    assert other_metrics.registry.get_sample_value("umbod_collector_requests_total", {
        "method": "POST", "route": "/v1/logs", "status_class": "4xx",
    }) is None


@pytest.mark.parametrize("operation", ["sink", "writer"])
def test_unexpected_ingestion_exception_preserves_failure_and_counts_one_request(
    collector: Collector, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    original_error = RuntimeError("private ingestion sentinel")

    def fail_export(batch: TelemetryExport) -> None:
        raise original_error

    async def fail_append(batch: LogWriteBatch) -> None:
        raise original_error

    if operation == "sink":
        monkeypatch.setattr(collector.sink, "export", fail_export)
    else:
        monkeypatch.setattr(collector.writer, "append_logs", fail_append)
    with pytest.raises(RuntimeError) as caught:
        collector.client.post("/v1/logs", json=MessageToDict(_logs(2)), headers={
            "Authorization": "Bearer credential-sentinel",
        })
    assert caught.value is original_error
    labels = {"method": "POST", "route": "/v1/logs", "status_class": "5xx"}
    assert collector.metrics.registry.get_sample_value("umbod_collector_requests_total", labels) == 1
    assert collector.metrics.registry.get_sample_value("umbod_collector_request_duration_seconds_count", labels) == 1
    assert collector.metrics.registry.get_sample_value("umbod_collector_log_records_accepted_total") == 0


@pytest.mark.parametrize("failure_receiver_fails", [False, True])
def test_completed_request_receiver_failure_does_not_change_response(
    monkeypatch: pytest.MonkeyPatch, failure_receiver_fails: bool,
) -> None:
    failure_channel = create_application_failure_signal()
    failures: list[ApplicationFailure] = []

    def fail_request(event: CompletedCollectorRequest) -> None:
        raise RuntimeError("private metric sentinel")

    def fail_diagnostic(event: ApplicationFailure) -> None:
        raise RuntimeError("private diagnostic sentinel")

    def provide_failures() -> Signal[ApplicationFailure]:
        return failure_channel

    if failure_receiver_fails:
        failure_channel.connect("test.diagnostic.failure", fail_diagnostic)
    failure_channel.connect("test.diagnostic.observer", failures.append)
    monkeypatch.setattr(
        "umbod.rest.telemetry.composition.create_application_failure_signal", provide_failures,
    )
    monkeypatch.setattr(PrometheusCollectorMetrics, "record_request", staticmethod(fail_request))
    app = FastAPI()
    metrics = PrometheusRestMetricsRecorder()
    install_telemetry_receiver_with_registry(app, AppConfig(otlp_receiver=OtlpReceiverConfig(
        enabled=True, bearer_token="credential-sentinel",
    )), metrics.registry)
    def provide_sink() -> TelemetrySink:
        return RecordingSink()

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    response = TestClient(app).post("/v1/logs", json={}, headers={
        "Authorization": "Bearer credential-sentinel",
    })
    assert response.status_code == 200
    assert response.json() == {}
    assert len(failures) == 1
    assert "private metric sentinel" not in failures[0].model_dump_json()
    assert "private diagnostic sentinel" not in failures[0].model_dump_json()


def test_repeated_standalone_factories_do_not_duplicate_registrations() -> None:
    settings = TelemetryAppConfig(
        runtime=RuntimeConfig(),
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="credential-sentinel"),
        telemetry_analytics=TelemetryAnalyticsConfig(),
    )
    first = create_telemetry_app(settings)
    second = create_telemetry_app(settings)
    assert first is not second
    first_publisher = first.dependency_overrides[get_accepted_logs_publisher]()
    second_publisher = second.dependency_overrides[get_accepted_logs_publisher]()
    assert first_publisher is not second_publisher
    first_events: list[AcceptedCollectorLogs] = []
    second_events: list[AcceptedCollectorLogs] = []
    first_publisher.connect("test.observer", first_events.append)
    second_publisher.connect("test.observer", second_events.append)
    def provide_sink() -> TelemetrySink:
        return RecordingSink()

    for app in (first, second):
        app.dependency_overrides[get_telemetry_sink] = provide_sink
        with TestClient(app) as client:
            response = client.post("/v1/logs", json={}, headers={
                "Authorization": "Bearer credential-sentinel",
            })
            assert response.status_code == 200
    assert first_events == [AcceptedCollectorLogs(0)]
    assert second_events == [AcceptedCollectorLogs(0)]


def test_receiver_failure_is_isolated_and_publishes_sanitized_failure() -> None:
    failures: list[ApplicationFailure] = []

    failure_channel = create_application_failure_signal()
    failure_channel.connect("test.failures", failures.append)
    signal = Signal[AcceptedCollectorLogs](PublishingSignalFailureHandler(failure_channel))
    observed: list[AcceptedCollectorLogs] = []

    def fail(event: AcceptedCollectorLogs) -> None:
        raise RuntimeError("credential-sentinel payload-sentinel")

    signal.connect("collector.logs.metrics", fail)
    signal.connect("test.observer", observed.append)
    signal.send(AcceptedCollectorLogs(2))
    assert observed == [AcceptedCollectorLogs(2)]
    assert len(failures) == 1
    assert "credential-sentinel" not in failures[0].model_dump_json()
    assert "payload-sentinel" not in failures[0].model_dump_json()
