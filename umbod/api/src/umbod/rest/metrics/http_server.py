import asyncio

from prometheus_client import CONTENT_TYPE_LATEST
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from uvicorn import Config, Server

from umbod.rest.metrics.recorder import RestMetricsExposer


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
        task = asyncio.create_task(server.serve())
        self._server = server
        self._task = task
        try:
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("REST metrics HTTP server stopped before startup")
                await asyncio.sleep(0)
        except BaseException:
            self._server = None
            self._task = None
            raise

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        server = self._server
        if server is not None:
            server.should_exit = True
        try:
            await task
        finally:
            self._server = None
            self._task = None


def create_rest_metrics_app(recorder: RestMetricsExposer) -> Starlette:
    async def metrics(_request: object) -> Response:
        return Response(
            recorder.prometheus_text(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    return Starlette(routes=[Route("/metrics", metrics, methods=["GET"])])
