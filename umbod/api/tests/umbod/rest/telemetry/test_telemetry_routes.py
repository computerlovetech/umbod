import gzip
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import JsonValue
from pytest import MonkeyPatch

from umbod.config import AppConfig, OtlpReceiverConfig, RuntimeConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySink, TelemetryUnavailable
from umbod.rest.main import create_app
from umbod.rest.telemetry import install_telemetry_receiver
from umbod.rest.telemetry.dependencies import get_telemetry_sink


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        if batch.item_count:
            self.batches.append(batch)


class UnavailableSink:
    def export(self, batch: TelemetryExport) -> None:
        raise TelemetryUnavailable("Unavailable")


def _client(config: AppConfig, sink: TelemetrySink) -> TestClient:
    app = FastAPI()
    install_telemetry_receiver(app, config)

    def provide_sink() -> TelemetrySink:
        return sink

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    return TestClient(app)


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="ingestion-secret")
    )


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def client(config: AppConfig, sink: RecordingSink) -> TestClient:
    return _client(config, sink)


_EXPORTS: list[tuple[str, dict[str, JsonValue]]] = [
    (
        "logs",
        {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "claude-code"},
                            }
                        ]
                    },
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "timeUnixNano": "18446744073709551615",
                                    "body": {"stringValue": "api_request"},
                                    "attributes": [
                                        {
                                            "key": "event.name",
                                            "value": {"stringValue": "api_request"},
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    ),
    (
        "metrics",
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "claude_code.token.usage",
                                    "sum": {
                                        "aggregationTemporality": 1,
                                        "isMonotonic": True,
                                        "dataPoints": [
                                            {
                                                "asInt": "9223372036854775807",
                                                "attributes": [
                                                    {
                                                        "key": "type",
                                                        "value": {
                                                            "stringValue": "input"
                                                        },
                                                    }
                                                ],
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        },
    ),
    (
        "traces",
        {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "claude_code.interaction",
                                    "traceId": "1234567890abcdef1234567890abcdef",
                                    "spanId": "1234567890abcdef",
                                    "kind": 1,
                                    "startTimeUnixNano": "100",
                                    "endTimeUnixNano": "200",
                                }
                            ]
                        }
                    ]
                }
            ]
        },
    ),
]


@pytest.mark.parametrize("export_case", _EXPORTS)
@pytest.mark.parametrize("compressed", [False, True])
def test_all_signals_accept_json_and_preserve_payload(
    client: TestClient,
    sink: RecordingSink,
    export_case: tuple[str, dict[str, JsonValue]],
    compressed: bool,
) -> None:
    signal, payload = export_case
    body = json.dumps(payload).encode()
    headers = {
        "Authorization": "Bearer ingestion-secret",
        "Content-Type": "application/json; charset=utf-8",
    }
    if compressed:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    response = client.post(f"/v1/{signal}", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == {}
    assert response.headers["content-type"] == "application/json"
    assert len(sink.batches) == 1
    assert sink.batches[0].signal.value == signal
    assert sink.batches[0].payload == payload
    assert sink.batches[0].item_count == 1


@pytest.mark.parametrize(
    "authorization", ["", "Basic ingestion-secret", "Bearer incorrect", "Bearer"]
)
def test_invalid_authentication_rejects_before_parsing(
    client: TestClient, sink: RecordingSink, authorization: str
) -> None:
    response = client.post(
        "/v1/logs", content="not-json", headers={"Authorization": authorization}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert set(response.json()) == {"code", "message"}
    assert not sink.batches
    assert "ingestion-secret" not in response.text


def test_duplicate_authorization_headers_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/logs",
        json={},
        headers=[
            ("Authorization", "Bearer ingestion-secret"),
            ("Authorization", "Bearer ingestion-secret"),
        ],
    )
    assert response.status_code == 401


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_empty_exports_are_successful_without_logging(
    client: TestClient, sink: RecordingSink, signal: str
) -> None:
    response = client.post(
        f"/v1/{signal}", json={}, headers={"Authorization": "Bearer ingestion-secret"}
    )
    assert response.status_code == 200
    assert not sink.batches


def test_unsupported_media_type_returns_415(
    client: TestClient, sink: RecordingSink
) -> None:
    response = client.post(
        "/v1/logs",
        content=b"protobuf",
        headers={
            "Authorization": "Bearer ingestion-secret",
            "Content-Type": "application/x-protobuf",
        },
    )
    assert response.status_code == 415
    assert not sink.batches


def test_invalid_batch_returns_400_without_partial_logging(
    client: TestClient, sink: RecordingSink
) -> None:
    response = client.post(
        "/v1/logs",
        json={
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {"body": {"stringValue": "valid"}},
                                {"body": {"boolValue": "invalid"}},
                            ]
                        }
                    ]
                }
            ]
        },
        headers={"Authorization": "Bearer ingestion-secret"},
    )
    assert response.status_code == 400
    assert set(response.json()) == {"code", "message"}
    assert "invalid" not in response.text
    assert not sink.batches


def test_disabled_receiver_is_unavailable(sink: RecordingSink) -> None:
    response = _client(AppConfig(), sink).post("/v1/logs", json={})
    assert response.status_code == 503
    assert not sink.batches


def test_explicit_local_development_allows_unauthenticated_ingestion(
    sink: RecordingSink,
) -> None:
    config = AppConfig(
        otlp_receiver=OtlpReceiverConfig(enabled=True, allow_unauthenticated=True)
    )
    response = _client(config, sink).post("/v1/logs", json=_EXPORTS[0][1])
    assert response.status_code == 200
    assert len(sink.batches) == 1


def test_direct_production_config_cannot_enable_unauthenticated_ingestion(
    sink: RecordingSink,
) -> None:
    config = AppConfig(
        runtime=RuntimeConfig(profile="production"),
        otlp_receiver=OtlpReceiverConfig(enabled=True, allow_unauthenticated=True),
    )
    with pytest.raises(ValueError, match="only allowed locally"):
        _client(config, sink)


def test_unavailable_logger_returns_retryable_503(config: AppConfig) -> None:
    response = _client(config, UnavailableSink()).post(
        "/v1/logs",
        json=_EXPORTS[0][1],
        headers={"Authorization": "Bearer ingestion-secret"},
    )
    assert response.status_code == 503
    assert set(response.json()) == {"code", "message"}


def test_oversized_payload_returns_413(config: AppConfig, sink: RecordingSink) -> None:
    config.otlp_receiver.max_request_bytes = 64
    response = _client(config, sink).post(
        "/v1/logs",
        json=_EXPORTS[0][1],
        headers={"Authorization": "Bearer ingestion-secret"},
    )
    assert response.status_code == 413
    assert not sink.batches


def test_receiver_is_mounted_on_root_application(
    config: AppConfig, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    deployment = tmp_path / "connector-availability.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    app = create_app(settings=config, connector_registrations=())
    response = TestClient(app).post("/v1/logs", json={})
    assert response.status_code == 401
