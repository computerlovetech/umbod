from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from umbod.config import AppConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry.analytics import TelemetryAnalyticsRuntime
from umbod.infrastructure.metrics.collector.prometheus import PrometheusCollectorMetrics


def create_collector_metrics_recorder() -> PrometheusCollectorMetrics:
    return PrometheusCollectorMetrics(CollectorRegistry())


def install_telemetry_receiver(app: FastAPI, config: AppConfig | TelemetryAppConfig) -> None:
    from umbod.rest.telemetry.composition import install_telemetry_receiver as install

    install(app, config, create_collector_metrics_recorder())


def install_telemetry_receiver_with_registry(
    app: FastAPI, config: AppConfig | TelemetryAppConfig, registry: CollectorRegistry,
) -> None:
    from umbod.rest.telemetry.composition import install_telemetry_receiver as install

    install(app, config, PrometheusCollectorMetrics(registry))


def create_receiver_app(
    settings: TelemetryAppConfig, runtime: TelemetryAnalyticsRuntime,
) -> FastAPI:
    from umbod.rest.telemetry.application import create_receiver_app as create

    return create(settings, runtime, create_collector_metrics_recorder())


def create_receiver_app_with_registry(
    settings: TelemetryAppConfig, runtime: TelemetryAnalyticsRuntime, registry: CollectorRegistry,
) -> FastAPI:
    from umbod.rest.telemetry.application import create_receiver_app as create

    return create(settings, runtime, PrometheusCollectorMetrics(registry))


def create_telemetry_app(settings: TelemetryAppConfig) -> FastAPI:
    from umbod.rest.telemetry.application import create_telemetry_app as create

    return create(settings, create_collector_metrics_recorder())
