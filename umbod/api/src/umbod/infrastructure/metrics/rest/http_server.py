import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import CONTENT_TYPE_LATEST
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from uvicorn import Config, Server as UvicornServer

from umbod.rest.metrics.recorder import RestMetricsExposer


class Server(UvicornServer):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


async def _serve_metrics(server: UvicornServer) -> None:
    try:
        await server.serve()
    except SystemExit:
        raise RuntimeError("REST metrics listener startup failed") from None


class RestMetricsHttpServer:
    def __init__(self, recorder: RestMetricsExposer, port: int) -> None:
        self._app = create_rest_metrics_app(recorder)
        self._port = port
        self._server: Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("REST metrics HTTP server is already running")
        server = Server(
            Config(
                self._app,
                host="0.0.0.0",
                port=self._port,
                lifespan="off",
                log_config=None,
            )
        )
        task = asyncio.create_task(_serve_metrics(server))
        self._server = server
        self._task = task
        try:
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError(
                        "REST metrics HTTP server stopped before startup"
                    )
                await asyncio.sleep(0)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        server = self._server
        if server is not None:
            server.should_exit = True
            if not server.started:
                task.cancel()
        try:
            done, pending = await asyncio.wait([task], timeout=10)
            if pending:
                task.cancel()
                raise TimeoutError("REST metrics listener shutdown timed out")
            if task in done and not task.cancelled():
                task.result()
        finally:
            if server is not None:
                for transport in getattr(server, "servers", []):
                    transport.close()
            self._server = None
            self._task = None


def create_rest_metrics_app(recorder: RestMetricsExposer) -> Starlette:
    async def metrics(_request: object) -> Response:
        return Response(
            recorder.prometheus_text(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    return Starlette(routes=[Route("/metrics", metrics, methods=["GET"])])
