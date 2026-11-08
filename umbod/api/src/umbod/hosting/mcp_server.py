import asyncio
import os
from functools import partial
from socket import socket

from uvicorn import Config
from uvicorn.supervisors import ChangeReload

from umbod.config import AppConfig, load_server_app_config
from umbod.hosting.listeners import HttpListener, capture_shutdown_signals, serve_listeners
from umbod.hosting.shutdown import ProcessShutdownDeadline
from umbod.logging import configure_logging
from umbod.mcp.administrator.application import build_administrator_app
from umbod.mcp.public_app import (
    build_starlette_app_with_shared_persistence,
    create_runtime_context,
    load_configured_public_app_config,
)
from umbod.mcp.runtime_adapters import (
    create_configured_downstream_client_factory,
    create_configured_openapi_runtime_adapters,
)


def validate_listener_ports(settings: AppConfig, port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("MCP listener port must be between 1 and 65535")
    reserved_ports = {settings.rest.port, settings.rest.metrics_port, settings.mcp.metrics_port}
    if settings.otlp_receiver.enabled:
        reserved_ports.add(settings.otlp_receiver.port)
    if port in reserved_ports:
        raise ValueError("MCP listener port must differ from REST, collector and metrics ports")
    if (
        settings.feature_toggles.mcp_administrator_enabled
        and settings.mcp_administrator.hosting == "separate"
        and settings.mcp_administrator.port in reserved_ports | {port}
    ):
        raise ValueError("Administrator MCP listener port must differ from other listener ports")


async def serve_mcp(
    settings: AppConfig,
    host: str,
    port: int,
    shutdown_requested: asyncio.Event,
) -> None:
    try:
        validate_listener_ports(settings, port)
        config = await load_configured_public_app_config(settings)
        try:
            if shutdown_requested.is_set():
                return
            async with asyncio.timeout(30):
                downstream_clients = await create_configured_downstream_client_factory(
                    settings, config.persistence_runtime.database
                )
                context = await create_runtime_context(
                    config,
                    downstream_client_factory=downstream_clients,
                    openapi_adapters=create_configured_openapi_runtime_adapters(settings),
                )
                application = await build_starlette_app_with_shared_persistence(context)
                listeners = [HttpListener(
                    name="mcp", app=application, host=host, port=port,
                    log_level=settings.runtime.log_level,
                )]
                if (
                    settings.feature_toggles.mcp_administrator_enabled
                    and settings.mcp_administrator.hosting == "separate"
                ):
                    administrator = await build_administrator_app(
                        settings, context.connector_runtime, config.persistence_runtime,
                        telemetry=config.telemetry,
                    )
                    listeners.append(HttpListener(
                        name="administrator-mcp", app=administrator,
                        host=settings.mcp_administrator.host,
                        port=settings.mcp_administrator.port,
                        log_level=settings.runtime.log_level,
                    ))
            await serve_listeners(tuple(listeners), shutdown_requested)
        finally:
            shutdown_requested.set()
            async with asyncio.timeout(10):
                await config.persistence_runtime.shutdown()
    finally:
        shutdown_requested.set()


async def _serve_with_signals(
    settings: AppConfig, host: str, port: int, deadline: ProcessShutdownDeadline,
) -> None:
    shutdown_requested = asyncio.Event()
    with capture_shutdown_signals(shutdown_requested):
        serving = asyncio.create_task(serve_mcp(settings, host, port, shutdown_requested))
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


def _run_configured_mcp(settings: AppConfig, host: str, port: int) -> None:
    deadline = ProcessShutdownDeadline(60, os._exit)
    try:
        asyncio.run(_serve_with_signals(settings, host, port, deadline))
    finally:
        deadline.cancel()


def _run_reloaded_mcp(*, host: str, port: int, sockets: list[socket]) -> None:
    if sockets:
        raise ValueError("The MCP host binds its own listener sockets")
    settings = load_server_app_config(".env")
    configure_logging(settings.runtime.app_name, settings.runtime.log_level)
    _run_configured_mcp(settings, host, port)


def run_mcp_server(settings: AppConfig, host: str, port: int, reload: bool) -> None:
    validate_listener_ports(settings, port)
    if reload:
        config = Config(
            "umbod.hosting.mcp_service:app", host=host, port=port, reload=True,
            workers=1, log_level=settings.runtime.log_level, log_config=None,
        )
        ChangeReload(
            config, target=partial(_run_reloaded_mcp, host=host, port=port), sockets=[],
        ).run()
        return
    _run_configured_mcp(settings, host, port)
