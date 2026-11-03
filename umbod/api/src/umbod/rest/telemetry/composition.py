from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from umbod.core.diagnostics import PublishingSignalFailureHandler
from umbod.core.signals import Signal, SignalPublisher
from umbod.logging import create_application_failure_signal
from umbod.rest.telemetry.metrics import PrometheusCollectorMetrics
from umbod.rest.telemetry.middleware import CollectorObservationsMiddleware
from umbod.rest.telemetry.observations import (
    AcceptedCollectorLogs, CompletedCollectorRequest, get_accepted_logs_publisher,
)

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
    install_telemetry_receiver_with_registry(app, config, CollectorRegistry())


def install_telemetry_receiver_with_registry(
    app: FastAPI, config: AppConfig | TelemetryAppConfig, registry: CollectorRegistry,
) -> None:
    if config.otlp_receiver.allow_unauthenticated and config.runtime.profile != "local":
        raise ValueError("Unauthenticated telemetry ingestion is only allowed locally")

    failure_handler = PublishingSignalFailureHandler(create_application_failure_signal())
    completed_requests = Signal[CompletedCollectorRequest](failure_handler)
    accepted_logs = Signal[AcceptedCollectorLogs](failure_handler)
    metrics = PrometheusCollectorMetrics(registry)
    completed_requests.connect("collector.requests.metrics", metrics.record_request)
    accepted_logs.connect("collector.logs.metrics", metrics.record_logs)

    def provide_accepted_logs() -> SignalPublisher[AcceptedCollectorLogs]:
        return accepted_logs

    app.dependency_overrides[get_accepted_logs_publisher] = provide_accepted_logs
    app.add_middleware(CollectorObservationsMiddleware, completed_requests=completed_requests)

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
