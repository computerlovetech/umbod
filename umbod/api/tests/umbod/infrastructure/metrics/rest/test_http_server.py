import asyncio
from unittest.mock import patch

import httpx
import pytest
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.testclient import TestClient
from uvicorn import Config, Server

from umbod.infrastructure.metrics.rest import PrometheusRestMetricsRecorder
from umbod.infrastructure.metrics.rest import RestMetricsHttpServer
from umbod.infrastructure.metrics.rest import create_rest_metrics_app


class _RecordingServer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.started = False
        self.should_exit = False

    async def serve(self) -> None:
        self.started = True
        while not self.should_exit:
            await asyncio.sleep(0)


@pytest.fixture
def recording_servers(monkeypatch: pytest.MonkeyPatch) -> list[_RecordingServer]:
    servers: list[_RecordingServer] = []

    def create_server(config: Config) -> _RecordingServer:
        server = _RecordingServer(config)
        servers.append(server)
        return server

    monkeypatch.setattr("umbod.infrastructure.metrics.rest.http_server.Server", create_server)
    return servers


@pytest.fixture
def uvicorn_servers(monkeypatch: pytest.MonkeyPatch) -> list[Server]:
    servers: list[Server] = []

    def create_server(config: Config) -> Server:
        server = Server(config)
        servers.append(server)
        return server

    monkeypatch.setattr("umbod.infrastructure.metrics.rest.http_server.Server", create_server)
    return servers


def test_metrics_app_serves_only_unauthenticated_prometheus_get_route() -> None:
    with TestClient(create_rest_metrics_app(PrometheusRestMetricsRecorder())) as client:
        metrics_response = client.get("/metrics")
        other_response = client.get("/health")
        post_response = client.post("/metrics")

    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert "umbod_rest_requests_total" in metrics_response.text
    assert "python_info" in metrics_response.text
    assert other_response.status_code == 404
    assert post_response.status_code == 405


@pytest.mark.asyncio
async def test_metrics_server_starts_and_stops_on_configured_port(
    uvicorn_servers: list[Server],
) -> None:
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 0)

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
        await server.stop()

    assert not listener.is_serving()


@pytest.mark.asyncio
async def test_metrics_server_rejects_duplicate_start() -> None:
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 0)

    await server.start()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            await server.start()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_metrics_server_clears_lifecycle_state_after_start_failure() -> None:
    class FailingServer:
        started = False
        should_exit = False

        def __init__(self, config: object) -> None:
            self.config = config

        async def serve(self) -> None:
            raise RuntimeError("bind failed")

    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 9876)

    with patch("umbod.infrastructure.metrics.rest.http_server.Server", FailingServer):
        with pytest.raises(RuntimeError, match="bind failed"):
            await server.start()
        await server.stop()
        with pytest.raises(RuntimeError, match="bind failed"):
            await server.start()


@pytest.mark.asyncio
async def test_metrics_server_configures_uvicorn_for_all_interfaces_and_configured_port(
    recording_servers: list[_RecordingServer],
) -> None:
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 9876)
    await server.start()
    await server.stop()

    config = recording_servers[0].config
    assert config.host == "0.0.0.0"
    assert config.port == 9876
    assert config.lifespan == "off"


@pytest.mark.asyncio
async def test_metrics_server_uses_fresh_uvicorn_server_after_stop(
    recording_servers: list[_RecordingServer],
) -> None:
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 9876)
    await server.start()
    await server.stop()
    await server.start()
    await server.stop()

    assert len(recording_servers) == 2
    assert recording_servers[0] is not recording_servers[1]
