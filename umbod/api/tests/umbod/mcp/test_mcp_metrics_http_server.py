import socket

import httpx
import pytest
from starlette.testclient import TestClient

from umbod.mcp.metrics.http_server import McpMetricsHttpServer, create_metrics_app
from umbod.mcp.metrics.prometheus import PrometheusMcpMetricsRecorder


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_metrics_app_serves_only_prometheus_metrics_route() -> None:
    recorder = PrometheusMcpMetricsRecorder()

    with TestClient(create_metrics_app(recorder)) as client:
        metrics_response = client.get("/metrics")
        other_response = client.get("/health")

    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain")
    assert "python_info" in metrics_response.text
    assert other_response.status_code == 404


@pytest.mark.asyncio
async def test_metrics_server_starts_and_stops_on_configured_port() -> None:
    port = _available_port()
    server = McpMetricsHttpServer(
        PrometheusMcpMetricsRecorder(),
        port,
        host="127.0.0.1",
    )

    await server.start()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://127.0.0.1:{port}/metrics")
    await server.stop()

    assert response.status_code == 200
    with pytest.raises(httpx.ConnectError):
        async with httpx.AsyncClient() as client:
            await client.get(f"http://127.0.0.1:{port}/metrics")
