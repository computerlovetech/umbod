from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry.analytics import TelemetryAnalyticsRuntime, TelemetryAnalyticsUnavailable
from umbod.infrastructure import create_configured_analytics_runtime
from umbod.logging import flush_logging
from umbod.rest.telemetry.composition import install_analytics_dependencies, install_telemetry_receiver


def create_receiver_app(
    settings: TelemetryAppConfig, runtime: TelemetryAnalyticsRuntime,
) -> FastAPI:
    app = FastAPI(title="Umbod telemetry", docs_url=None, redoc_url=None)
    install_telemetry_receiver(app, settings)
    install_analytics_dependencies(app, runtime)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        try:
            await runtime.ensure_ready()
        except TelemetryAnalyticsUnavailable:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    return app


def create_telemetry_app(settings: TelemetryAppConfig) -> FastAPI:
    runtime = create_configured_analytics_runtime(settings)
    app = create_receiver_app(settings, runtime)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            await runtime.ensure_ready()
            yield
        finally:
            try:
                flush_logging()
            finally:
                await runtime.shutdown()

    app.router.lifespan_context = lifespan
    return app
