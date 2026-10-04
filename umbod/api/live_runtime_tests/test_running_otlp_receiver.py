import gzip
import json
import os

import httpx
import pytest
from pydantic import JsonValue

from conftest import RuntimeEndpoints


@pytest.fixture(scope="session")
def otlp_bearer_token() -> str:
    return os.environ["UMBOD_TEST_OTLP_BEARER_TOKEN"]


_RUNTIME_SIGNALS: dict[str, tuple[str, str, str, dict[str, JsonValue]]] = {
    "logs": (
        "resourceLogs",
        "scopeLogs",
        "logRecords",
        {"body": {"stringValue": "runtime export"}},
    ),
    "metrics": (
        "resourceMetrics",
        "scopeMetrics",
        "metrics",
        {
            "name": "runtime.count",
            "sum": {
                "aggregationTemporality": 1,
                "isMonotonic": True,
                "dataPoints": [{"asInt": "1"}],
            },
        },
    ),
    "traces": (
        "resourceSpans",
        "scopeSpans",
        "spans",
        {
            "name": "runtime.operation",
            "traceId": "1234567890abcdef1234567890abcdef",
            "spanId": "1234567890abcdef",
            "kind": 1,
        },
    ),
}


def _runtime_export(signal: str) -> dict[str, JsonValue]:
    marker: dict[str, JsonValue] = {
        "attributes": [
            {
                "key": "test.marker",
                "value": {
                    "stringValue": f"umbod-otlp-runtime-{signal}",
                },
            }
        ],
    }
    resource_key, scope_key, item_key, item = _RUNTIME_SIGNALS[signal]
    return {resource_key: [{"resource": marker, scope_key: [{item_key: [item]}]}]}


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
@pytest.mark.parametrize("compressed", [False, True])
def test_running_receiver_accepts_authenticated_exports(
    runtime_endpoints: RuntimeEndpoints,
    otlp_bearer_token: str,
    signal: str,
    compressed: bool,
) -> None:
    body = json.dumps(_runtime_export(signal)).encode()
    headers = {
        "Authorization": f"Bearer {otlp_bearer_token}",
        "Content-Type": "application/json",
    }
    if compressed:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    response = httpx.post(
        f"{runtime_endpoints.api_base_url}/v1/{signal}",
        content=body,
        headers=headers,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {}
    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_running_receiver_requires_dedicated_credentials(
    runtime_endpoints: RuntimeEndpoints, signal: str
) -> None:
    response = httpx.post(
        f"{runtime_endpoints.api_base_url}/v1/{signal}",
        json={},
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"},
        timeout=10,
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("signal", ["logs", "metrics", "traces"])
def test_running_receiver_rejects_malformed_json(
    runtime_endpoints: RuntimeEndpoints, otlp_bearer_token: str, signal: str
) -> None:
    response = httpx.post(
        f"{runtime_endpoints.api_base_url}/v1/{signal}",
        content=b"not-json",
        headers={
            "Authorization": f"Bearer {otlp_bearer_token}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    assert response.status_code == 400
    assert set(response.json()) == {"code", "message"}
