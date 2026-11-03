import gzip
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.protobuf.message import Message
from google.rpc.status_pb2 import Status
from httpx import Response
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.core.telemetry import TelemetryExport, TelemetrySignal, TelemetryUnavailable
from umbod.core.telemetry.analytics import (
    LogDimension,
    LogWriteBatch,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
)
from umbod.rest.telemetry import install_telemetry_receiver
from umbod.rest.telemetry.dependencies import get_analytics_writer, get_telemetry_sink


class RecordingSink:
    def __init__(self, unavailable: bool = False) -> None:
        self.batches: list[TelemetryExport] = []
        self.unavailable = unavailable

    def export(self, batch: TelemetryExport) -> None:
        if self.unavailable:
            raise TelemetryUnavailable("private sink failure ingestion-secret")
        self.batches.append(batch)


class RecordingAnalyticsWriter:
    def __init__(self, unavailable: bool = False) -> None:
        self.batches: list[LogWriteBatch] = []
        self.unavailable = unavailable

    async def append_logs(self, batch: LogWriteBatch) -> None:
        if self.unavailable:
            raise TelemetryAnalyticsUnavailable(
                "private analytics failure ingestion-secret"
            )
        self.batches.append(batch)


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        otlp_receiver=OtlpReceiverConfig(enabled=True, bearer_token="ingestion-secret")
    )


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


@pytest.fixture
def writer() -> RecordingAnalyticsWriter:
    return RecordingAnalyticsWriter()


@contextmanager
def receiver_client(
    config: AppConfig, sink: RecordingSink, writer: RecordingAnalyticsWriter
) -> Iterator[TestClient]:
    app = FastAPI()
    install_telemetry_receiver(app, config)

    def provide_sink() -> RecordingSink:
        return sink

    def provide_writer() -> TelemetryAnalyticsWriter:
        return writer

    app.dependency_overrides[get_telemetry_sink] = provide_sink
    app.dependency_overrides[get_analytics_writer] = provide_writer
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(
    config: AppConfig, sink: RecordingSink, writer: RecordingAnalyticsWriter
) -> Iterator[TestClient]:
    with receiver_client(config, sink, writer) as receiver:
        yield receiver


def export_request(signal: TelemetrySignal) -> Message:
    if signal == TelemetrySignal.LOGS:
        request = ExportLogsServiceRequest()
        resource = request.resource_logs.add()
        resource.resource.attributes.add(
            key="service.name"
        ).value.string_value = "coding-agent"
        record = resource.scope_logs.add().log_records.add(
            severity_text="INFO", event_name="tool.called"
        )
        record.body.string_value = "private telemetry payload"
        record.attributes.add(key="session.id").value.string_value = "session-1"
        record.attributes.add(key="tool.name").value.string_value = "read-file"
        return request
    if signal == TelemetrySignal.METRICS:
        request = ExportMetricsServiceRequest()
        request.resource_metrics.add().scope_metrics.add().metrics.add(
            name="tokens"
        ).sum.data_points.add(as_int=2**63 - 1)
        return request
    request = ExportTraceServiceRequest()
    request.resource_spans.add().scope_spans.add().spans.add(
        name="operation", trace_id=b"\xab" * 16, span_id=b"\xcd" * 8
    )
    return request


def headers(encoding: str = "identity") -> dict[str, str]:
    return {
        "Content-Type": "application/x-protobuf",
        "Authorization": "Bearer ingestion-secret",
        "Content-Encoding": encoding,
    }


def assert_binary_error(
    response: Response, status_code: int, code: int, message: str
) -> None:
    assert response.status_code == status_code
    assert response.headers["content-type"] == "application/x-protobuf"
    status = Status.FromString(response.content)
    assert status.code == code
    assert status.message == message
    assert not status.details
    assert b"ingestion-secret" not in response.content
    assert b"private" not in response.content


@pytest.mark.parametrize(
    "signal,response_type",
    [
        (TelemetrySignal.LOGS, ExportLogsServiceResponse),
        (TelemetrySignal.METRICS, ExportMetricsServiceResponse),
        (TelemetrySignal.TRACES, ExportTraceServiceResponse),
    ],
)
@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_all_signals_accept_binary_exports_and_return_decodable_empty_success(
    client: TestClient,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    signal: TelemetrySignal,
    response_type: type[Message],
    encoding: str,
) -> None:
    body = export_request(signal).SerializeToString()
    response = client.post(
        f"/v1/{signal.value}",
        content=gzip.compress(body) if encoding == "gzip" else body,
        headers=headers(encoding),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-protobuf"
    assert response.content == b""
    assert response_type.FromString(response.content) == response_type()
    assert len(sink.batches) == 1
    assert sink.batches[0].signal == signal
    assert sink.batches[0].item_count == 1
    assert len(writer.batches) == (1 if signal == TelemetrySignal.LOGS else 0)


@pytest.mark.parametrize("signal", list(TelemetrySignal))
@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_zero_byte_exports_are_successful_without_analytics_writes(
    client: TestClient,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    signal: TelemetrySignal,
    encoding: str,
) -> None:
    response = client.post(
        f"/v1/{signal.value}",
        content=gzip.compress(b"") if encoding == "gzip" else b"",
        headers=headers(encoding),
    )
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"] == "application/x-protobuf"
    assert all(batch.item_count == 0 and batch.payload == {} for batch in sink.batches)
    assert not writer.batches


@pytest.mark.parametrize("signal", list(TelemetrySignal))
@pytest.mark.parametrize("body", [b"\xff", b"\x0a\x05x"])
def test_malformed_and_truncated_protobuf_never_reach_writers(
    client: TestClient,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    signal: TelemetrySignal,
    body: bytes,
) -> None:
    response = client.post(f"/v1/{signal.value}", content=body, headers=headers())
    assert_binary_error(response, 400, 3, "Invalid OTLP protobuf request")
    assert not sink.batches
    assert not writer.batches


@pytest.mark.parametrize(
    "authorization_headers",
    [
        [],
        [("Authorization", "")],
        [("Authorization", "Basic ingestion-secret")],
        [("Authorization", "Bearer incorrect")],
        [("Authorization", "Bearer")],
    ],
)
def test_authentication_errors_are_binary_before_parsing(
    client: TestClient,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    authorization_headers: list[tuple[str, str]],
) -> None:
    request_headers = headers("unsupported")
    request_headers.pop("Authorization")
    request_headers.update(authorization_headers)
    response = client.post("/v1/logs", content=b"\xffprivate", headers=request_headers)
    assert_binary_error(
        response,
        401,
        16,
        "Invalid bearer credentials"
        if authorization_headers == [("Authorization", "Bearer incorrect")]
        else "Bearer authentication is required",
    )
    assert response.headers["www-authenticate"] == "Bearer"
    assert not sink.batches
    assert not writer.batches


def test_duplicate_tokens_return_safe_binary_authentication_error(
    client: TestClient, sink: RecordingSink, writer: RecordingAnalyticsWriter
) -> None:
    response = client.post(
        "/v1/logs",
        content=b"\xff",
        headers=[
            ("Content-Type", "application/x-protobuf"),
            ("Authorization", "Bearer ingestion-secret"),
            ("Authorization", "Bearer ingestion-secret"),
        ],
    )
    assert_binary_error(response, 401, 16, "Bearer authentication is required")
    assert not sink.batches
    assert not writer.batches


def test_disabled_receiver_returns_safe_binary_unavailable(
    config: AppConfig, sink: RecordingSink, writer: RecordingAnalyticsWriter
) -> None:
    config.otlp_receiver.enabled = False
    with receiver_client(config, sink, writer) as client:
        response = client.post("/v1/logs", content=b"\xffprivate", headers=headers())
    assert_binary_error(response, 503, 14, "Telemetry ingestion is disabled")
    assert not sink.batches
    assert not writer.batches


@pytest.mark.parametrize("encoding", ["br", "deflate", "gzip, identity"])
def test_unsupported_encoding_returns_binary_error_without_writes(
    client: TestClient,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    encoding: str,
) -> None:
    response = client.post("/v1/logs", content=b"private", headers=headers(encoding))
    assert_binary_error(response, 415, 3, "Unsupported content encoding")
    assert not sink.batches
    assert not writer.batches


@pytest.mark.parametrize(
    "body",
    [
        b"not gzip private",
        gzip.compress(b"")[:-1],
        gzip.compress(b"") + b"private",
        gzip.compress(b"") + gzip.compress(b""),
    ],
)
def test_invalid_gzip_returns_safe_binary_error_without_writes(
    client: TestClient,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    body: bytes,
) -> None:
    response = client.post("/v1/logs", content=body, headers=headers("gzip"))
    assert_binary_error(response, 400, 3, "Invalid gzip body")
    assert not sink.batches
    assert not writer.batches


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
@pytest.mark.parametrize("declared_length", [True, False])
def test_wire_size_limit_applies_with_and_without_content_length(
    config: AppConfig,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    encoding: str,
    declared_length: bool,
) -> None:
    body = export_request(TelemetrySignal.LOGS).SerializeToString()
    wire = gzip.compress(body) if encoding == "gzip" else body
    config.otlp_receiver.max_request_bytes = len(wire) - 1
    with receiver_client(config, sink, writer) as client:
        request = client.build_request(
            "POST", "/v1/logs", content=wire, headers=headers(encoding)
        )
        if not declared_length:
            del request.headers["content-length"]
        response = client.send(request)
    assert_binary_error(response, 413, 8, "Telemetry request too large")
    assert not sink.batches
    assert not writer.batches


def test_decompressed_size_limit_applies_to_small_compressed_export(
    config: AppConfig, sink: RecordingSink, writer: RecordingAnalyticsWriter
) -> None:
    request = ExportLogsServiceRequest()
    request.resource_logs.add().scope_logs.add().log_records.add().body.string_value = (
        "x" * 4096
    )
    body = request.SerializeToString()
    wire = gzip.compress(body)
    config.otlp_receiver.max_request_bytes = 256
    assert len(wire) < config.otlp_receiver.max_request_bytes < len(body)
    with receiver_client(config, sink, writer) as client:
        response = client.post("/v1/logs", content=wire, headers=headers("gzip"))
    assert_binary_error(response, 413, 8, "Telemetry request too large")
    assert not sink.batches
    assert not writer.batches


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_export_at_request_size_limit_is_accepted(
    config: AppConfig,
    sink: RecordingSink,
    writer: RecordingAnalyticsWriter,
    encoding: str,
) -> None:
    body = export_request(TelemetrySignal.LOGS).SerializeToString()
    wire = gzip.compress(body) if encoding == "gzip" else body
    config.otlp_receiver.max_request_bytes = max(len(wire), len(body))
    with receiver_client(config, sink, writer) as client:
        response = client.post("/v1/logs", content=wire, headers=headers(encoding))
    assert response.status_code == 200
    assert len(sink.batches) == 1
    assert len(writer.batches) == 1


def test_missing_configured_token_returns_safe_binary_unavailable(
    config: AppConfig, sink: RecordingSink, writer: RecordingAnalyticsWriter
) -> None:
    config.otlp_receiver.bearer_token = ""
    with receiver_client(config, sink, writer) as client:
        response = client.post("/v1/logs", content=b"\xffprivate", headers=headers())
    assert_binary_error(response, 503, 14, "Telemetry authentication is not configured")
    assert not sink.batches
    assert not writer.batches


@pytest.mark.parametrize("signal", list(TelemetrySignal))
def test_sink_failure_returns_safe_binary_unavailable_before_analytics(
    config: AppConfig, writer: RecordingAnalyticsWriter, signal: TelemetrySignal
) -> None:
    sink = RecordingSink(unavailable=True)
    with receiver_client(config, sink, writer) as client:
        response = client.post(
            f"/v1/{signal.value}",
            content=export_request(signal).SerializeToString(),
            headers=headers(),
        )
    assert_binary_error(response, 503, 14, "Telemetry logging is unavailable")
    assert not writer.batches


def test_analytics_failure_returns_safe_binary_unavailable(
    config: AppConfig, sink: RecordingSink
) -> None:
    writer = RecordingAnalyticsWriter(unavailable=True)
    with receiver_client(config, sink, writer) as client:
        response = client.post(
            "/v1/logs",
            content=export_request(TelemetrySignal.LOGS).SerializeToString(),
            headers=headers(),
        )
    assert_binary_error(response, 503, 14, "Telemetry analytics is unavailable")
    assert len(sink.batches) == 1


def test_binary_logs_are_normalized_into_analytics_dimensions(
    client: TestClient, writer: RecordingAnalyticsWriter
) -> None:
    response = client.post(
        "/v1/logs",
        content=export_request(TelemetrySignal.LOGS).SerializeToString(),
        headers=headers(),
    )
    assert response.status_code == 200
    assert len(writer.batches) == 1
    assert len(writer.batches[0].records) == 1
    assert {
        group.dimension: group.value.value
        for group in writer.batches[0].records[0].dimensions
    } == {
        LogDimension.SOURCE: "coding-agent",
        LogDimension.EVENT_NAME: "tool.called",
        LogDimension.SESSION_ID: "session-1",
        LogDimension.TOOL_NAME: "read-file",
        LogDimension.SEVERITY: "INFO",
    }
