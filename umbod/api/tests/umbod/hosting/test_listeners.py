import asyncio
import signal
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
from typing import Optional

import httpx
import pytest
from fastapi import FastAPI, Request

from umbod.hosting import listeners as hosting
from umbod.hosting.listeners import HttpListener, run_listeners, serve_listeners


@pytest.fixture
def addresses(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    captured: list[tuple[str, int]] = []
    bind = socket.socket.bind

    def capture(bound: socket.socket, address: tuple[str, int]) -> None:
        bind(bound, address)
        if address[1] == 0:
            captured.append(bound.getsockname())

    monkeypatch.setattr(socket.socket, "bind", capture)
    return captured


def _listener(name: str, app: FastAPI) -> HttpListener:
    return HttpListener(
        name=name, app=app, host="127.0.0.1", port=0, log_level="warning"
    )


async def _response(
    addresses: list[tuple[str, int]], index: int, path: str
) -> httpx.Response:
    async with asyncio.timeout(3):
        while True:
            if len(addresses) > index:
                host, port = addresses[index]
                try:
                    async with httpx.AsyncClient(trust_env=False) as client:
                        return await client.get(f"http://{host}:{port}{path}")
                except httpx.TransportError:
                    pass
            await asyncio.sleep(0.01)


def _assert_released(addresses: list[tuple[str, int]]) -> None:
    for address in addresses:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(address)


@asynccontextmanager
async def _running(
    listeners: tuple[HttpListener, ...],
) -> AsyncIterator[tuple[asyncio.Task[None], asyncio.Event]]:
    shutdown = asyncio.Event()
    task = asyncio.create_task(serve_listeners(listeners, shutdown))
    try:
        yield task, shutdown
    finally:
        shutdown.set()
        await asyncio.wait_for(task, 4)


def test_listener_is_immutable_data() -> None:
    listener = _listener("first", FastAPI())
    with pytest.raises(FrozenInstanceError):
        listener.port = 1234


@pytest.mark.asyncio
async def test_listeners_keep_routes_separate_and_preserve_lifespan_state(
    addresses: list[tuple[str, int]],
) -> None:
    active: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        active.append(app.title)
        try:
            yield {"owner": app.title}
        finally:
            active.remove(app.title)

    first = FastAPI(title="first", lifespan=lifespan)
    second = FastAPI(title="second", lifespan=lifespan)

    @first.get("/first")
    @second.get("/second")
    async def identity(request: Request) -> dict[str, object]:
        original = request.state.owner
        request.state.owner = "request-local"
        return {"owner": original, "active": list(active)}

    async with _running((_listener("first", first), _listener("second", second))):
        for index, name in enumerate(("first", "second")):
            for _ in range(2):
                response = await _response(addresses, index, f"/{name}")
                assert response.json() == {"owner": name, "active": ["first", "second"]}
            other = "second" if index == 0 else "first"
            assert (await _response(addresses, index, f"/{other}")).status_code == 404
    assert active == []
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_readiness_waits_for_every_listener(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    starting = asyncio.Event()
    startup = hosting._ListenerServer.startup

    async def delayed_startup(
        server: hosting._ListenerServer, sockets: Optional[list[socket.socket]] = None
    ) -> None:
        if server.config.app.app.title == "second":
            starting.set()
            await release.wait()
        await startup(server, sockets)

    monkeypatch.setattr(hosting._ListenerServer, "startup", delayed_startup)
    first = FastAPI(title="first")
    second = FastAPI(title="second")

    @first.get("/system/health")
    @first.get("/api/system/health")
    @first.get("/ready")
    @second.get("/ready")
    async def healthy() -> dict[str, bool]:
        return {"ready": True}

    async with _running((_listener("first", first), _listener("second", second))):
        await asyncio.wait_for(starting.wait(), 2)
        for path in ("/system/health", "/api/system/health", "/ready"):
            assert (await _response(addresses, 0, path)).status_code == 503
        release.set()
        async with asyncio.timeout(3):
            while (await _response(addresses, 0, "/ready")).status_code != 200:
                await asyncio.sleep(0.01)
        assert (await _response(addresses, 1, "/ready")).status_code == 200
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_occupied_second_port_releases_first_and_sanitizes_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, int]] = []
    original_bind = socket.socket.bind

    def capture(bound: socket.socket, address: tuple[str, int]) -> None:
        original_bind(bound, address)
        captured.append(bound.getsockname())

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        monkeypatch.setattr(socket.socket, "bind", capture)
        listeners = (
            _listener("first", FastAPI()),
            HttpListener(
                "second", FastAPI(), "127.0.0.1", occupied.getsockname()[1], "warning"
            ),
        )
        with pytest.raises(
            RuntimeError, match="^Unable to bind HTTP listeners$"
        ) as failure:
            await serve_listeners(listeners, asyncio.Event())
        assert failure.value.__suppress_context__
        monkeypatch.setattr(socket.socket, "bind", original_bind)
        assert len(captured) == 1
        _assert_released(captured)


@pytest.mark.asyncio
async def test_lifespan_startup_failure_exits_previous_lifespan_and_releases_ports(
    addresses: list[tuple[str, int]],
) -> None:
    exited = asyncio.Event()

    @asynccontextmanager
    async def first_lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            exited.set()

    @asynccontextmanager
    async def failing_lifespan(app: FastAPI) -> AsyncIterator[None]:
        raise RuntimeError("startup failed")
        yield

    listeners = (
        _listener("first", FastAPI(lifespan=first_lifespan)),
        _listener("second", FastAPI(lifespan=failing_lifespan)),
    )
    with pytest.raises(RuntimeError, match="startup failed"):
        await serve_listeners(listeners, asyncio.Event())
    assert exited.is_set()
    _assert_released(addresses)


@pytest.mark.asyncio
@pytest.mark.parametrize("raises", [False, True])
async def test_listener_exit_during_startup_stops_sibling(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch, raises: bool
) -> None:
    exit_server = asyncio.Event()
    serve = hosting._ListenerServer.serve

    async def interrupted_serve(
        server: hosting._ListenerServer, sockets: Optional[list[socket.socket]] = None
    ) -> None:
        if server.config.app.app.title == "second":
            await exit_server.wait()
            if raises:
                raise RuntimeError("listener failed")
            return
        await serve(server, sockets)

    monkeypatch.setattr(hosting._ListenerServer, "serve", interrupted_serve)
    task = asyncio.create_task(
        serve_listeners(
            (
                _listener("first", FastAPI()),
                _listener("second", FastAPI(title="second")),
            ),
            asyncio.Event(),
        )
    )
    try:
        await _response(addresses, 0, "/missing")
        exit_server.set()
        with pytest.raises(RuntimeError, match="listener failed|stopped unexpectedly"):
            await asyncio.wait_for(task, 3)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_running_listener_exit_stops_sibling(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_server = asyncio.Event()
    main_loop = hosting._ListenerServer.main_loop

    async def interrupted_main_loop(server: hosting._ListenerServer) -> None:
        if server.config.app.app.title == "second":
            await exit_server.wait()
            return
        await main_loop(server)

    monkeypatch.setattr(hosting._ListenerServer, "main_loop", interrupted_main_loop)
    first = FastAPI()
    second = FastAPI(title="second")

    @first.get("/ready")
    async def ready() -> bool:
        return True

    task = asyncio.create_task(
        serve_listeners(
            (_listener("first", first), _listener("second", second)), asyncio.Event()
        )
    )
    try:
        async with asyncio.timeout(3):
            while (await _response(addresses, 0, "/ready")).status_code != 200:
                await asyncio.sleep(0.01)
        exit_server.set()
        with pytest.raises(RuntimeError, match="stopped unexpectedly"):
            await asyncio.wait_for(task, 3)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    _assert_released(addresses)


@pytest.mark.asyncio
@pytest.mark.parametrize("during_startup", [False, True])
async def test_cancellation_releases_ports_and_exits_lifespans(
    addresses: list[tuple[str, int]], during_startup: bool
) -> None:
    entered = asyncio.Event()
    exited = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        entered.set()
        try:
            if during_startup:
                await asyncio.Event().wait()
            yield
        finally:
            exited.set()

    task = asyncio.create_task(
        serve_listeners(
            (_listener("first", FastAPI(lifespan=lifespan)),), asyncio.Event()
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if not during_startup:
            await _response(addresses, 0, "/missing")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert exited.is_set()
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_shutdown_drains_requests_before_exiting_lifespan(
    addresses: list[tuple[str, int]],
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    exited = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            exited.set()

    app = FastAPI(lifespan=lifespan)

    @app.get("/slow")
    async def slow() -> dict[str, bool]:
        entered.set()
        await release.wait()
        return {"lifespan_active": not exited.is_set()}

    async with _running((_listener("first", app), _listener("second", FastAPI()))) as (
        task,
        shutdown,
    ):
        request = asyncio.create_task(_response(addresses, 0, "/slow"))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            shutdown.set()
            await asyncio.sleep(0.05)
            assert not exited.is_set()
            assert not task.done()
            release.set()
            assert (await request).json() == {"lifespan_active": True}
        finally:
            release.set()
            await asyncio.gather(request, return_exceptions=True)
    assert exited.is_set()
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_unresponsive_server_is_cancelled_and_releases_ports(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    cancelled = asyncio.Event()
    monkeypatch.setattr(hosting, "DRAIN_TIMEOUT", 0.01)

    async def unresponsive_main_loop(server: hosting._ListenerServer) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(hosting._ListenerServer, "main_loop", unresponsive_main_loop)
    async with _running((_listener("first", FastAPI()),)) as (_, shutdown):
        await _response(addresses, 0, "/missing")
        shutdown.set()
    assert cancelled.is_set()
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_blocked_lifespan_exits_time_out_and_every_lifespan_is_attempted(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "CLEANUP_TIMEOUT", 0.05)
    attempted: list[str] = []
    cancelled: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            attempted.append(app.title)
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(app.title)

    shutdown = asyncio.Event()
    task = asyncio.create_task(
        serve_listeners(
            (
                _listener("first", FastAPI(title="first", lifespan=lifespan)),
                _listener("second", FastAPI(title="second", lifespan=lifespan)),
            ),
            shutdown,
        )
    )
    try:
        await _response(addresses, 0, "/missing")
        shutdown.set()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(task, 3)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert attempted == ["second", "first"]
    assert cancelled == attempted
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_blocked_request_cleanup_times_out_and_releases_ports(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "DRAIN_TIMEOUT", 0.01)
    monkeypatch.setattr(hosting, "CLEANUP_TIMEOUT", 0.05)
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_completed = asyncio.Event()

    async def unresponsive_main_loop(server: hosting._ListenerServer) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(hosting._ListenerServer, "main_loop", unresponsive_main_loop)
    app = FastAPI()

    @app.get("/blocked")
    async def blocked() -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
                await release_cleanup.wait()
                cleanup_completed.set()

    shutdown = asyncio.Event()
    task = asyncio.create_task(serve_listeners((_listener("first", app),), shutdown))
    request = asyncio.create_task(_response(addresses, 0, "/blocked"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        shutdown.set()
        with pytest.raises((TimeoutError, ExceptionGroup)):
            await asyncio.wait_for(task, 3)
        assert cancelled.is_set()
        assert not cleanup_completed.is_set()
        _assert_released(addresses)
    finally:
        release_cleanup.set()
        request.cancel()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, request, return_exceptions=True)
        await asyncio.wait_for(cleanup_completed.wait(), 1)


@pytest.mark.asyncio
async def test_lifespan_cancellation_cleanup_does_not_extend_deadline(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "CLEANUP_TIMEOUT", 0.05)
    cancelled = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
                await release.wait()
                completed.set()

    shutdown = asyncio.Event()
    task = asyncio.create_task(
        serve_listeners((_listener("first", FastAPI(lifespan=lifespan)),), shutdown)
    )
    try:
        await _response(addresses, 0, "/missing")
        shutdown.set()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(task, 2)
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not completed.is_set()
        _assert_released(addresses)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.wait_for(completed.wait(), 1)


@pytest.mark.asyncio
async def test_shutdown_failure_closes_idle_connections_and_stops_sibling(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "CLEANUP_TIMEOUT", 0.1)
    shutdown_server = hosting._ListenerServer.shutdown
    exited: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            exited.append(app.title)

    async def failing_shutdown(
        server: hosting._ListenerServer, sockets: list[socket.socket]
    ) -> None:
        if server.config.app.app.title == "first":
            raise RuntimeError("shutdown failed")
        await shutdown_server(server, sockets)

    monkeypatch.setattr(hosting._ListenerServer, "shutdown", failing_shutdown)
    shutdown = asyncio.Event()
    task = asyncio.create_task(
        serve_listeners(
            (
                _listener("first", FastAPI(title="first", lifespan=lifespan)),
                _listener("second", FastAPI(title="second", lifespan=lifespan)),
            ),
            shutdown,
        )
    )
    try:
        await _response(addresses, 0, "/missing")
        reader, writer = await asyncio.open_connection(*addresses[0])
        try:
            writer.write(b"GET /missing HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 1)
            shutdown.set()
            with pytest.raises(RuntimeError, match="shutdown failed"):
                await asyncio.wait_for(task, 2)
            assert await asyncio.wait_for(reader.read(), 1)
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert exited == ["second", "first"]
    _assert_released(addresses)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_internal_exit_signals_watchdog_before_awaiting_cleanup(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch, cancelled: bool
) -> None:
    closing = asyncio.Event()
    release = asyncio.Event()
    fail = asyncio.Event()
    shutdown = asyncio.Event()
    close = hosting._ListenerHost.close

    async def delayed_close(host: hosting._ListenerHost) -> None:
        closing.set()
        await release.wait()
        await close(host)

    async def failing_main_loop(server: hosting._ListenerServer) -> None:
        await fail.wait()
        raise RuntimeError("listener failed")

    monkeypatch.setattr(hosting._ListenerHost, "close", delayed_close)
    monkeypatch.setattr(hosting._ListenerServer, "main_loop", failing_main_loop)
    task = asyncio.create_task(
        serve_listeners((_listener("first", FastAPI()),), shutdown)
    )
    try:
        await _response(addresses, 0, "/missing")
        if cancelled:
            task.cancel()
        else:
            fail.set()
        await asyncio.wait_for(closing.wait(), 2)
        assert shutdown.is_set()
        assert not task.done()
    finally:
        release.set()
        fail.set()
        if cancelled:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        else:
            with pytest.raises(RuntimeError, match="listener failed"):
                await asyncio.wait_for(task, 2)
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_shutdown_rejects_readiness_before_servers_stop_accepting(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    closing = asyncio.Event()
    release = asyncio.Event()
    close = hosting._ListenerHost.close

    async def delayed_close(host: hosting._ListenerHost) -> None:
        closing.set()
        await release.wait()
        await close(host)

    monkeypatch.setattr(hosting._ListenerHost, "close", delayed_close)
    app = FastAPI()

    @app.get("/ready")
    async def ready() -> bool:
        return True

    async with _running((_listener("first", app),)) as (_, shutdown):
        async with asyncio.timeout(3):
            while (await _response(addresses, 0, "/ready")).status_code != 200:
                await asyncio.sleep(0.01)
        shutdown.set()
        try:
            await asyncio.wait_for(closing.wait(), 2)
            assert (await _response(addresses, 0, "/ready")).status_code == 503
        finally:
            release.set()
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_startup_timeout_releases_ports(
    addresses: list[tuple[str, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosting, "STARTUP_TIMEOUT", 0.05)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await asyncio.Event().wait()
        yield

    with pytest.raises(TimeoutError):
        await serve_listeners(
            (_listener("first", FastAPI(lifespan=lifespan)),), asyncio.Event()
        )
    _assert_released(addresses)


@pytest.mark.asyncio
async def test_signal_capture_covers_initialization_before_listeners_exist() -> None:
    shutdown = asyncio.Event()
    previous = signal.getsignal(signal.SIGINT)
    with hosting.capture_shutdown_signals(shutdown):
        signal.raise_signal(signal.SIGINT)
        await asyncio.wait_for(shutdown.wait(), 1)
    assert signal.getsignal(signal.SIGINT) == previous


def test_signal_capture_skips_worker_threads() -> None:
    def capture() -> bool:
        shutdown = asyncio.Event()
        with hosting.capture_shutdown_signals(shutdown):
            return not shutdown.is_set()

    async def worker() -> bool:
        return await asyncio.to_thread(capture)

    assert asyncio.run(worker())


@pytest.mark.parametrize("fails", [False, True])
def test_run_restores_signal_handlers(
    monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    previous = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }

    async def stop(
        listeners: tuple[HttpListener, ...], shutdown_requested: asyncio.Event
    ) -> None:
        signal.raise_signal(signal.SIGTERM)
        await asyncio.wait_for(shutdown_requested.wait(), 1)
        if fails:
            raise RuntimeError("host failed")

    monkeypatch.setattr(hosting, "serve_listeners", stop)
    if fails:
        with pytest.raises(RuntimeError, match="host failed"):
            run_listeners((_listener("first", FastAPI()),))
    else:
        run_listeners((_listener("first", FastAPI()),))
    assert {signum: signal.getsignal(signum) for signum in previous} == previous
