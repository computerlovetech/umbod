import asyncio
from collections.abc import Iterator
from contextlib import contextmanager, suppress

from prometheus_client import CONTENT_TYPE_LATEST
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from uvicorn import Config, Server as UvicornServer

from umbod.mcp.metrics.prometheus import PrometheusMcpMetricsRecorder


class Server(UvicornServer):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


async def _serve_metrics(server: UvicornServer) -> None:
    try:
        await server.serve()
    except SystemExit:
        raise RuntimeError("MCP metrics listener startup failed") from None


class McpMetricsHttpServer:
    def __init__(
        self,
        recorder: PrometheusMcpMetricsRecorder,
        port: int,
        host: str,
    ) -> None:
        self._server = Server(
            Config(
                create_metrics_app(recorder),
                host=host,
                port=port,
                lifespan="off",
                log_config=None,
            )
        )
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("MCP metrics HTTP server is already running")
        self._task = asyncio.create_task(_serve_metrics(self._server))
        try:
            while not self._server.started:
                if self._task.done():
                    await self._task
                    raise RuntimeError("MCP metrics HTTP server stopped before startup")
                await asyncio.sleep(0)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._server.should_exit = True
        if not self._server.started:
            task.cancel()
        try:
            done, pending = await asyncio.wait([task], timeout=10)
            if pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise TimeoutError("MCP metrics listener shutdown timed out")
            if task in done and not task.cancelled():
                task.result()
        finally:
            for transport in getattr(self._server, 'servers', []):
                transport.close()
            self._task = None


def create_metrics_app(recorder: PrometheusMcpMetricsRecorder) -> Starlette:
    async def metrics(_request: object) -> Response:
        return Response(
            recorder.prometheus_text(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    return Starlette(routes=[Route("/metrics", metrics, methods=["GET"])])
