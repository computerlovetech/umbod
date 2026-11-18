from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink
from umbod.rest.telemetry import install_telemetry_receiver
from umbod.rest.telemetry.dependencies import get_telemetry_sink
from umbod.rest.telemetry import AcceptedCollectorLogs, CompletedCollectorRequest


class RecordingCollectorMetrics:
    def __init__(self) -> None:
        self.requests: list[CompletedCollectorRequest] = []
        self.logs: list[AcceptedCollectorLogs] = []

    def record_request(self, event: CompletedCollectorRequest) -> None:
        self.requests.append(event)

    def record_logs(self, event: AcceptedCollectorLogs) -> None:
        self.logs.append(event)


class RecordingSink:
    def export(self, batch: TelemetryExport) -> None:
        pass


def test_receiver_records_observations_through_injected_metrics() -> None:
    metrics = RecordingCollectorMetrics()
    app = FastAPI()
    install_telemetry_receiver(app, AppConfig(otlp_receiver=OtlpReceiverConfig(
        enabled=True, bearer_token="collector-test-token",
    )), metrics)

    def provide_sink() -> TelemetrySink:
        return RecordingSink()

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    with TestClient(app) as client:
        response = client.post("/v1/logs", json={}, headers={
            "Authorization": "Bearer collector-test-token",
        })
    assert response.status_code == 200
    assert metrics.logs == [AcceptedCollectorLogs(0)]
    assert len(metrics.requests) == 1
    request = metrics.requests[0]
    assert (request.method, request.route, request.status_class) == ("POST", "/v1/logs", "2xx")
    assert request.duration_seconds >= 0


def test_receiver_records_rejected_request_without_accepted_logs() -> None:
    metrics = RecordingCollectorMetrics()
    app = FastAPI()
    install_telemetry_receiver(app, AppConfig(otlp_receiver=OtlpReceiverConfig(
        enabled=True, bearer_token="collector-test-token",
    )), metrics)
    with TestClient(app) as client:
        response = client.post("/v1/logs", json={})
    assert response.status_code == 401
    assert metrics.logs == []
    assert len(metrics.requests) == 1
    assert metrics.requests[0].status_class == "4xx"
