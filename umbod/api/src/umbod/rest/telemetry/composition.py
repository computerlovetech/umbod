from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.core.telemetry.analytics import (
    TelemetryAnalyticsReader,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsWriter,
)
from umbod.infrastructure import create_disabled_analytics_runtime
from umbod.rest.telemetry.dependencies import (
    get_analytics_reader,
    get_analytics_writer,
    get_receiver_config,
)
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.routes import router

_STATUS_CODES = {400: 3, 401: 16, 413: 8, 415: 3, 503: 14}


async def telemetry_error_response(
    request: Request, exception: Exception
) -> JSONResponse:
    if not isinstance(exception, TelemetryHttpError):
        raise exception
    headers = {"WWW-Authenticate": "Bearer"} if exception.status_code == 401 else {}
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "code": _STATUS_CODES[exception.status_code],
            "message": exception.message,
        },
        headers=headers,
    )


def install_telemetry_receiver(app: FastAPI, config: AppConfig) -> None:
    if config.otlp_receiver.allow_unauthenticated and config.runtime.profile != "local":
        raise ValueError("Unauthenticated telemetry ingestion is only allowed locally")

    def provide_receiver_config() -> OtlpReceiverConfig:
        return config.otlp_receiver

    install_analytics_dependencies(app, create_disabled_analytics_runtime())
    app.dependency_overrides[get_receiver_config] = provide_receiver_config
    app.add_exception_handler(TelemetryHttpError, telemetry_error_response)
    app.include_router(router)


def install_analytics_dependencies(app: FastAPI, runtime: TelemetryAnalyticsRuntime) -> None:
    def provide_writer() -> TelemetryAnalyticsWriter:
        return runtime.create_writer()

    def provide_reader() -> TelemetryAnalyticsReader:
        return runtime.create_reader()

    app.dependency_overrides[get_analytics_writer] = provide_writer
    app.dependency_overrides[get_analytics_reader] = provide_reader
