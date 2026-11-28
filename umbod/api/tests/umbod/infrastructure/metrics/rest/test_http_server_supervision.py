import asyncio
import signal
import socket

import pytest

from umbod.infrastructure.metrics.rest import PrometheusRestMetricsRecorder
from umbod.infrastructure.metrics.rest import RestMetricsHttpServer
from umbod.infrastructure.metrics.rest.http_server import Server


def _signal_handlers() -> tuple[object, object]:
    return signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)


@pytest.mark.asyncio
async def test_embedded_metrics_listener_does_not_replace_process_signal_handlers() -> None:
    previous = _signal_handlers()
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 0)
    try:
        await server.start()
        assert _signal_handlers() == previous
    finally:
        await server.stop()
    assert _signal_handlers() == previous


@pytest.mark.asyncio
async def test_cancelled_metrics_startup_stops_the_owned_server_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starting = asyncio.Event()
    finished = asyncio.Event()

    class DelayedServer(Server):
        async def startup(self, sockets: object) -> None:
            starting.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

    monkeypatch.setattr("umbod.infrastructure.metrics.rest.http_server.Server", DelayedServer)
    server = RestMetricsHttpServer(PrometheusRestMetricsRecorder(), 0)
    startup = asyncio.create_task(server.start())
    await asyncio.wait_for(starting.wait(), timeout=1)
    startup.cancel()
    with pytest.raises(asyncio.CancelledError):
        await startup
    await asyncio.wait_for(finished.wait(), timeout=1)
    await server.stop()


@pytest.mark.asyncio
async def test_occupied_metrics_port_raises_without_exiting_the_process() -> None:
    with socket.socket() as occupied:
        occupied.bind(("0.0.0.0", 0))
        occupied.listen()
        server = RestMetricsHttpServer(
            PrometheusRestMetricsRecorder(), occupied.getsockname()[1]
        )
        with pytest.raises(RuntimeError, match="metrics listener startup failed"):
            await server.start()
        await server.stop()
