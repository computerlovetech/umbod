import asyncio
import os
from functools import partial
from socket import socket

from uvicorn import Config
from uvicorn.supervisors import ChangeReload

from umbod.config import AppConfig, load_server_app_config
from umbod.config.telemetry import TelemetryAppConfig
from umbod.hosting.listeners import (
    HttpListener,
    capture_shutdown_signals,
    serve_listeners,
)
from umbod.hosting.shutdown import ProcessShutdownDeadline
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider, create_configured_analytics_runtime
from umbod.logging import configure_logging
from umbod.rest.main import create_app_with_shared_persistence
from umbod.rest.metrics import PrometheusRestMetricsRecorder
from umbod.rest.telemetry.application import create_receiver_app_with_registry
from umbod.rest.telemetry.token_authentication import install_telemetry_token_verifier


def validate_listener_ports(settings: AppConfig, port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("REST listener port must be between 1 and 65535")
    reserved_ports = {
        settings.mcp.port,
        settings.rest.metrics_port,
        settings.mcp.metrics_port,
    }
    if port in reserved_ports:
        raise ValueError("REST listener port must differ from MCP and metrics ports")
    if (
        settings.otlp_receiver.enabled
        and settings.otlp_receiver.port in reserved_ports | {port}
    ):
        raise ValueError(
            "Collector listener port must differ from REST, MCP and metrics ports"
        )


async def serve_api(
    settings: AppConfig,
    host: str,
    port: int,
    shutdown_requested: asyncio.Event,
) -> None:
    validate_listener_ports(settings, port)
    runtime = create_configured_analytics_runtime(settings)
    persistence = ConfiguredPersistenceRuntimeProvider(settings.connector_store).create()
    try:
        async with asyncio.timeout(30):
            await runtime.ensure_ready()
            await persistence.readiness.ensure_ready()
        if shutdown_requested.is_set():
            return
        metrics_recorder = PrometheusRestMetricsRecorder()
        api = create_app_with_shared_persistence(
            persistence, runtime, metrics_recorder, settings=settings,
        )
        listeners = [
            HttpListener(
                name="api",
                app=api,
                host=host,
                port=port,
                log_level=settings.runtime.log_level,
            )
        ]
        if settings.otlp_receiver.enabled:
            collector_settings = TelemetryAppConfig(
                runtime=settings.runtime,
                otlp_receiver=settings.otlp_receiver,
                telemetry_analytics=settings.telemetry_analytics,
            )
            collector = create_receiver_app_with_registry(collector_settings, runtime, metrics_recorder.registry)
            install_telemetry_token_verifier(collector, persistence, settings)
            listeners.append(
                HttpListener(
                    name="collector",
                    app=collector,
                    host=settings.otlp_receiver.host,
                    port=settings.otlp_receiver.port,
                    log_level=settings.runtime.log_level,
                )
            )
        await serve_listeners(tuple(listeners), shutdown_requested)
    finally:
        shutdown_requested.set()
        async with asyncio.timeout(10):
            try:
                await runtime.shutdown()
            finally:
                await persistence.shutdown()


async def _serve_with_signals(
    settings: AppConfig,
    host: str,
    port: int,
    deadline: ProcessShutdownDeadline,
) -> None:
    shutdown_requested = asyncio.Event()
    with capture_shutdown_signals(shutdown_requested):
        serving = asyncio.create_task(
            serve_api(settings, host, port, shutdown_requested)
        )
        stopping = asyncio.create_task(shutdown_requested.wait())
        try:
            await asyncio.wait([serving, stopping], return_when=asyncio.FIRST_COMPLETED)
            if stopping.done():
                deadline.arm()
            await serving
        finally:
            deadline.arm()
            shutdown_requested.set()
            stopping.cancel()
            await asyncio.gather(stopping, return_exceptions=True)
            if not serving.done():
                _, pending = await asyncio.wait([serving], timeout=30)
                for task in pending:
                    task.cancel()


def _run_configured_api(settings: AppConfig, host: str, port: int) -> None:
    deadline = ProcessShutdownDeadline(60, os._exit)
    try:
        asyncio.run(_serve_with_signals(settings, host, port, deadline))
    finally:
        deadline.cancel()


def _run_reloaded_api(*, host: str, port: int, sockets: list[socket]) -> None:
    if sockets:
        raise ValueError("The API host binds its own listener sockets")
    settings = load_server_app_config(".env")
    configure_logging(settings.runtime.app_name, settings.runtime.log_level)
    _run_configured_api(settings, host, port)


def run_api_server(settings: AppConfig, host: str, port: int, reload: bool) -> None:
    validate_listener_ports(settings, port)
    if reload:
        config = Config(
            "umbod.hosting.rest_service:create_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            workers=1,
            log_level=settings.runtime.log_level,
            log_config=None,
        )
        ChangeReload(
            config,
            target=partial(_run_reloaded_api, host=host, port=port),
            sockets=[],
        ).run()
        return
    _run_configured_api(settings, host, port)
