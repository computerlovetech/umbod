import asyncio
import signal
import socket
import sys
import threading
from collections.abc import AsyncIterator, Awaitable, Iterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass

import uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

STARTUP_TIMEOUT = 30.0
DRAIN_TIMEOUT = 10.0
CLEANUP_TIMEOUT = 5.0
_READINESS_PATHS = frozenset({"/system/health", "/api/system/health", "/ready"})


@dataclass(frozen=True)
class HttpListener:
    name: str
    app: Starlette
    host: str
    port: int
    log_level: str


class _ListenerApp:
    def __init__(
        self,
        app: Starlette,
        state: Mapping[str, object],
        ready: asyncio.Event,
        shutdown_requested: asyncio.Event,
    ) -> None:
        self.app = app
        self.state = state
        self.ready = ready
        self.shutdown_requested = shutdown_requested

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["path"] in _READINESS_PATHS
            and (not self.ready.is_set() or self.shutdown_requested.is_set())
        ):
            await Response(status_code=503)(scope, receive, send)
            return
        if scope["type"] in {"http", "websocket"}:
            scope = dict(scope)
            scope["state"] = {**scope.get("state", {}), **self.state}
        await self.app(scope, receive, send)


class _ListenerServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self.listening = asyncio.Event()

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield

    async def startup(self, sockets: list[socket.socket]) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            self.listening.set()


def _bind(listeners: tuple[HttpListener, ...]) -> list[socket.socket]:
    sockets: list[socket.socket] = []
    try:
        for listener in listeners:
            family, kind, protocol, _, address = socket.getaddrinfo(
                listener.host, listener.port, type=socket.SOCK_STREAM
            )[0]
            bound = socket.socket(family, kind, protocol)
            sockets.append(bound)
            bound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            bound.bind(address)
            bound.setblocking(False)
    except OSError:
        for bound in sockets:
            bound.close()
        raise RuntimeError("Unable to bind HTTP listeners") from None
    return sockets


async def _serve_server(server: _ListenerServer, bound: socket.socket) -> None:
    try:
        await server.serve(sockets=[bound])
    except SystemExit:
        raise RuntimeError("HTTP listener startup failed") from None


def _check_servers(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        if task.done():
            task.result()
            raise RuntimeError("HTTP listener stopped unexpectedly")


@asynccontextmanager
async def _bounded_lifespan(app: Starlette) -> AsyncIterator[Mapping[str, object]]:
    started: asyncio.Future[Mapping[str, object]] = asyncio.get_running_loop().create_future()
    stopping = asyncio.Event()

    async def run() -> None:
        try:
            async with app.router.lifespan_context(app) as state:
                if not started.done():
                    started.set_result(state or {})
                await stopping.wait()
        except BaseException as error:
            if not started.done():
                started.set_exception(error)
            raise

    task = asyncio.create_task(run())
    try:
        try:
            state = await started
        except BaseException:
            task.cancel()
            raise
        yield state
    finally:
        stopping.set()
        await _wait_cleanup(task)


def _consume_result(task: asyncio.Future[object]) -> None:
    if not task.cancelled():
        task.exception()


async def _wait_cleanup(operation: Awaitable[object]) -> None:
    task = asyncio.ensure_future(operation)
    try:
        async with asyncio.timeout(CLEANUP_TIMEOUT):
            await asyncio.shield(task)
    except BaseException:
        task.cancel()
        task.add_done_callback(_consume_result)
        raise


async def _attempt_cleanup(
    operation: Awaitable[object], errors: list[Exception]
) -> None:
    try:
        await _wait_cleanup(operation)
    except Exception as error:
        errors.append(error)


async def _finish_tasks(
    tasks: list[asyncio.Task[None]], errors: list[Exception]
) -> None:
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, timeout=CLEANUP_TIMEOUT)
    for task in pending:
        task.cancel()
        task.add_done_callback(_consume_result)
    if pending:
        errors.append(
            TimeoutError("HTTP listener tasks did not stop before the cleanup deadline")
        )
    for task in done:
        if not task.cancelled():
            error = task.exception()
            if isinstance(error, Exception):
                errors.append(error)
            elif error is not None:
                raise error


class _ListenerHost:
    def __init__(
        self,
        listeners: tuple[HttpListener, ...],
        sockets: list[socket.socket],
        shutdown_requested: asyncio.Event,
    ) -> None:
        self.listeners = listeners
        self.sockets = sockets
        self.shutdown_requested = shutdown_requested
        self.stack = AsyncExitStack()
        self.ready = asyncio.Event()
        self.servers: list[_ListenerServer] = []
        self.tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        async with asyncio.timeout(STARTUP_TIMEOUT):
            for listener in self.listeners:
                state = await self.stack.enter_async_context(
                    _bounded_lifespan(listener.app)
                )
                server = _ListenerServer(
                    uvicorn.Config(
                        _ListenerApp(
                            listener.app, state, self.ready, self.shutdown_requested
                        ),
                        host=listener.host,
                        port=listener.port,
                        lifespan="off",
                        log_config=None,
                        access_log=True,
                        log_level=listener.log_level,
                        timeout_graceful_shutdown=DRAIN_TIMEOUT,
                    )
                )
                self.servers.append(server)
            self.tasks = [
                asyncio.create_task(_serve_server(server, bound))
                for server, bound in zip(self.servers, self.sockets, strict=True)
            ]
            for server in self.servers:
                listening = asyncio.create_task(server.listening.wait())
                try:
                    await asyncio.wait(
                        [listening, *self.tasks], return_when=asyncio.FIRST_COMPLETED
                    )
                    _check_servers(self.tasks)
                    await listening
                finally:
                    listening.cancel()
                    listening.add_done_callback(_consume_result)
            _check_servers(self.tasks)
            if not self.shutdown_requested.is_set():
                self.ready.set()

    async def close(self) -> None:
        self.ready.clear()
        errors: list[Exception] = []
        for server in self.servers:
            server.should_exit = True
        try:
            if self.tasks:
                _, pending = await asyncio.wait(self.tasks, timeout=DRAIN_TIMEOUT + 1)
                for task in pending:
                    task.cancel()
                await _finish_tasks(self.tasks, errors)
            transports = [
                transport
                for server in self.servers
                for transport in getattr(server, "servers", [])
            ]
            for transport in transports:
                try:
                    transport.close()
                except Exception as error:
                    errors.append(error)
            for server in self.servers:
                for connection in list(server.server_state.connections):
                    try:
                        connection.shutdown()
                    except Exception as error:
                        errors.append(error)
            request_tasks = [
                task for server in self.servers for task in server.server_state.tasks
            ]
            for task in request_tasks:
                task.cancel()
            await _finish_tasks(request_tasks, errors)
            for transport in transports:
                await _attempt_cleanup(transport.wait_closed(), errors)
        finally:
            try:
                for bound in self.sockets:
                    try:
                        bound.close()
                    except OSError as error:
                        errors.append(error)
            finally:
                try:
                    await self.stack.aclose()
                except Exception as error:
                    errors.append(error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("HTTP listener cleanup failed", errors)


async def serve_listeners(
    listeners: tuple[HttpListener, ...], shutdown_requested: asyncio.Event
) -> None:
    try:
        if not listeners:
            raise ValueError("At least one HTTP listener is required")
        host = _ListenerHost(listeners, _bind(listeners), shutdown_requested)
    except BaseException:
        shutdown_requested.set()
        raise
    startup = asyncio.create_task(host.start())
    shutdown = asyncio.create_task(shutdown_requested.wait())
    try:
        completed, _ = await asyncio.wait(
            [startup, shutdown],
            timeout=STARTUP_TIMEOUT,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not completed:
            raise TimeoutError(
                "HTTP listeners did not start before the startup deadline"
            )
        if startup.done():
            await startup
        if shutdown.done():
            return
        await startup
        await asyncio.wait([shutdown, *host.tasks], return_when=asyncio.FIRST_COMPLETED)
        _check_servers(host.tasks)
    finally:
        shutdown_requested.set()
        primary_error = sys.exception()
        host.ready.clear()
        startup.cancel()
        shutdown.cancel()
        errors: list[Exception] = []
        await _finish_tasks([startup, shutdown], errors)
        cleanup = asyncio.create_task(host.close())
        try:
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise
            if errors:
                raise errors[0]
        except Exception as cleanup_error:
            if primary_error is cleanup_error:
                raise
            if primary_error is not None:
                raise primary_error from cleanup_error
            raise


@contextmanager
def capture_shutdown_signals(shutdown_requested: asyncio.Event) -> Iterator[None]:
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    loop = asyncio.get_running_loop()

    def request_shutdown(signum: int, frame: object) -> None:
        loop.call_soon_threadsafe(shutdown_requested.set)

    previous = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        for signum in previous:
            signal.signal(signum, request_shutdown)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


async def _run(listeners: tuple[HttpListener, ...]) -> None:
    shutdown_requested = asyncio.Event()
    with capture_shutdown_signals(shutdown_requested):
        await serve_listeners(listeners, shutdown_requested)


def run_listeners(listeners: tuple[HttpListener, ...]) -> None:
    asyncio.run(_run(listeners))
