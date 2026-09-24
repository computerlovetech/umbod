import asyncio
import socket
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.testclient import TestClient

from umbod.rest.metrics import (
    PrometheusRestMetricsRecorder,
    RestMetricsHttpServer,
    create_rest_metrics_app,
)


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


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
async def test_metrics_server_starts_and_stops_on_configured_port() -> None:
    port = _available_port()
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), port)

    await server.start()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://127.0.0.1:{port}/metrics")
    await server.stop()
    await server.stop()

    assert response.status_code == 200
    with pytest.raises(httpx.ConnectError):
        async with httpx.AsyncClient() as client:
            await client.get(f"http://127.0.0.1:{port}/metrics")


@pytest.mark.asyncio
async def test_metrics_server_rejects_duplicate_start() -> None:
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), _available_port())

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

    with patch("umbod.rest.metrics.http_server.Server", FailingServer):
        with pytest.raises(RuntimeError, match="bind failed"):
            await server.start()
        await server.stop()
        with pytest.raises(RuntimeError, match="bind failed"):
            await server.start()


@pytest.mark.asyncio
async def test_metrics_server_configures_uvicorn_for_all_interfaces_and_configured_port() -> None:
    captured_config: dict[str, Any] = {}

    class CapturingConfig:
        def __init__(self, app: object, **kwargs: object) -> None:
            captured_config.update(kwargs)

    class CapturingServer:
        started = False
        should_exit = False

        def __init__(self, config: object) -> None:
            captured_config["server_config"] = config

        async def serve(self) -> None:
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(0)

    with (
        patch("umbod.rest.metrics.http_server.Config", CapturingConfig),
        patch("umbod.rest.metrics.http_server.Server", CapturingServer),
    ):
        server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 9876)
        await server.start()
        await server.stop()

    assert captured_config["host"] == "0.0.0.0"
    assert captured_config["port"] == 9876
    assert captured_config["lifespan"] == "off"


@pytest.mark.asyncio
async def test_metrics_server_uses_fresh_uvicorn_server_after_stop() -> None:
    created_servers: list[object] = []

    class RestartableServer:
        started = False
        should_exit = False

        def __init__(self, config: object) -> None:
            self.config = config
            created_servers.append(self)

        async def serve(self) -> None:
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(0)

    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 9876)
    with patch("umbod.rest.metrics.http_server.Server", RestartableServer):
        await server.start()
        await server.stop()
        await server.start()
        await server.stop()

    assert len(created_servers) == 2
    assert created_servers[0] is not created_servers[1]
