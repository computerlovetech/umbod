import asyncio
import signal
import socket
from unittest.mock import Mock

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


@pytest.mark.asyncio
async def test_metrics_listener_never_replaces_process_signal_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    install_handler = Mock(wraps=signal.signal)
    monkeypatch.setattr(signal, 'signal', install_handler)
    server = McpMetricsHttpServer(PrometheusMcpMetricsRecorder(), 0, host='127.0.0.1')
    await server.start()
    try:
        install_handler.assert_not_called()
    finally:
        await server.stop()
    install_handler.assert_not_called()


@pytest.mark.asyncio
async def test_metrics_bind_failure_is_reported_and_cleans_background_task() -> None:
    initial_tasks = asyncio.all_tasks()
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        server = McpMetricsHttpServer(PrometheusMcpMetricsRecorder(), port, host='127.0.0.1')
        with pytest.raises(RuntimeError, match='MCP metrics listener startup failed'):
            await server.start()
        await server.stop()
    assert asyncio.all_tasks() == initial_tasks
