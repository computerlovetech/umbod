import gzip
from uuid import uuid4

import httpx
import pytest
from google.protobuf.message import Message
from google.rpc.status_pb2 import Status
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.resource.v1.resource_pb2 import Resource

from conftest import RuntimeEndpoints


def _request(signal: str) -> Message:
    resource = Resource(
        attributes=[
            {
                "key": "service.name",
                "value": {"string_value": "umbod-otlp-protobuf-runtime"},
            },
            {
                "key": "test.marker",
                "value": {"string_value": f"umbod-otlp-protobuf-runtime-{signal}"},
            },
        ]
    )
    if signal == "logs":
        return ExportLogsServiceRequest(
            resource_logs=[
                {
                    "resource": resource,
                    "scope_logs": [
                        {
                            "log_records": [
                                {
                                    "severity_text": "INFO",
                                    "event_name": "hermes.tool.completed",
                                    "attributes": [
                                        {
                                            "key": "session.id",
                                            "value": {
                                                "string_value": "protobuf-runtime-session"
                                            },
                                        },
                                        {
                                            "key": "tool.name",
                                            "value": {"string_value": "shell"},
                                        },
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        )
    if signal == "metrics":
        return ExportMetricsServiceRequest(
            resource_metrics=[
                {
                    "resource": resource,
                    "scope_metrics": [
                        {
                            "metrics": [
                                {
                                    "name": "runtime.count",
                                    "sum": {
                                        "aggregation_temporality": 1,
                                        "data_points": [{"as_int": 1}],
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        )
    return ExportTraceServiceRequest(
        resource_spans=[
            {
                "resource": resource,
                "scope_spans": [
                    {
                        "spans": [
                            {
                                "name": "runtime.operation",
                                "trace_id": bytes.fromhex(
                                    "1234567890abcdef1234567890abcdef"
                                ),
                                "span_id": bytes.fromhex("1234567890abcdef"),
                                "kind": 1,
                            }
                        ]
                    }
                ],
            }
        ]
    )


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
@pytest.mark.parametrize("compressed", [False, True])
def test_running_receiver_accepts_protobuf_exports(
    runtime_endpoints: RuntimeEndpoints,
    otlp_bearer_token: str,
    signal: str,
    compressed: bool,
) -> None:
    body = _request(signal).SerializeToString()
    headers = {
        "Authorization": f"Bearer {otlp_bearer_token}",
        "Content-Type": "application/x-protobuf",
    }
    if compressed:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    response = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/{signal}",
        content=body,
        headers=headers,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.content == b""
    assert response.headers["content-type"] == "application/x-protobuf"


def test_running_protobuf_logs_are_queryable_in_analytics(
    runtime_endpoints: RuntimeEndpoints,
    otlp_bearer_token: str,
) -> None:
    source = f"protobuf-analytics-{uuid4().hex}"
    request = ExportLogsServiceRequest(
        resource_logs=[
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"string_value": source}},
                    ]
                },
                "scope_logs": [
                    {
                        "log_records": [
                            {
                                "time_unix_nano": 1767226200000000000,
                                "event_name": "tool.completed",
                                "attributes": [
                                    {
                                        "key": "tool.name",
                                        "value": {"string_value": "shell"},
                                    },
                                    {
                                        "key": "session.id",
                                        "value": {"string_value": "session-protobuf"},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    )
    exported = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs",
        content=request.SerializeToString(),
        headers={
            "Authorization": f"Bearer {otlp_bearer_token}",
            "Content-Type": "application/x-protobuf",
        },
        timeout=10,
    )
    assert exported.status_code == 200, exported.text
    result = httpx.post(
        f"{runtime_endpoints.api_base_url}/api/admin/telemetry/log-counts",
        json={
            "time_range": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
            "filters": [{"dimension": "source", "values": [source]}],
            "group_by": ["event_name", "session_id", "tool_name"],
            "bucketing": {"kind": "none"},
            "max_groups": 10,
        },
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"},
        timeout=10,
    )
    assert result.status_code == 200, result.text
    assert result.json() == {
        "rows": [
            {
                "groups": [
                    {
                        "dimension": "event_name",
                        "value": {"kind": "present", "value": "tool.completed"},
                    },
                    {
                        "dimension": "session_id",
                        "value": {"kind": "present", "value": "session-protobuf"},
                    },
                    {
                        "dimension": "tool_name",
                        "value": {"kind": "present", "value": "shell"},
                    },
                ],
                "count": 1,
                "bucket": {"kind": "none"},
            }
        ]
    }


def test_running_receiver_rejects_protobuf_with_wrong_credential(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    response = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs",
        content=b"invalid",
        headers={
            "Authorization": f"Bearer {runtime_endpoints.bearer_token}",
            "Content-Type": "application/x-protobuf",
        },
        timeout=10,
    )
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/x-protobuf"
    assert Status.FromString(response.content).code == 16
    assert response.headers["www-authenticate"] == "Bearer"
