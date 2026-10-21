import httpx
import pytest
from starlette.testclient import TestClient
from uvicorn import Config, Server

from umbod.mcp.metrics.http_server import McpMetricsHttpServer, create_metrics_app
from umbod.mcp.metrics.prometheus import PrometheusMcpMetricsRecorder


@pytest.fixture
def uvicorn_servers(monkeypatch: pytest.MonkeyPatch) -> list[Server]:
    servers: list[Server] = []

    def create_server(config: Config) -> Server:
        server = Server(config)
        servers.append(server)
        return server

    monkeypatch.setattr("umbod.mcp.metrics.http_server.Server", create_server)
    return servers


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
async def test_metrics_server_starts_and_stops_on_configured_port(
    uvicorn_servers: list[Server],
) -> None:
    server = McpMetricsHttpServer(
        PrometheusMcpMetricsRecorder(),
        0,
        host="127.0.0.1",
    )

    await server.start()
    try:
        assert uvicorn_servers[0].config.port == 0
        listener = uvicorn_servers[0].servers[0]
        port = listener.sockets[0].getsockname()[1]
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{port}/metrics")
        assert response.status_code == 200
    finally:
        await server.stop()

    assert not listener.is_serving()
