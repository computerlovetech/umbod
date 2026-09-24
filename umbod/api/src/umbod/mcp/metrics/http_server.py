import asyncio

from prometheus_client import CONTENT_TYPE_LATEST
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from uvicorn import Config, Server

from umbod.mcp.metrics.prometheus import PrometheusMcpMetricsRecorder


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
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            if self._task.done():
                await self._task
                raise RuntimeError("MCP metrics HTTP server stopped before startup")
            await asyncio.sleep(0)

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._server.should_exit = True
        await task
        self._task = None


def create_metrics_app(recorder: PrometheusMcpMetricsRecorder) -> Starlette:
    async def metrics(_request: object) -> Response:
        return Response(
            recorder.prometheus_text(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    return Starlette(routes=[Route("/metrics", metrics, methods=["GET"])])
