from fastapi import FastAPI

from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.config.telemetry import TelemetryAppConfig
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
from umbod.rest.telemetry.responses import telemetry_error_response
from umbod.rest.telemetry.routes import router


def install_telemetry_receiver(app: FastAPI, config: AppConfig | TelemetryAppConfig) -> None:
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
