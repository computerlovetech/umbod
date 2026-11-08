import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from umbod.build_identity import UMBOD_RELEASE
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.persistence import PersistenceRuntime
from umbod.http_metadata import HttpMetadataStarlette
from umbod.mcp.administrator.composition import register_configured_administrator_tools
from umbod.mcp.auth import MCPAuthProviderFactory
from umbod.mcp.auth.consent_screen import install_umbod_consent_screen
from umbod.mcp.http_transport import MAX_MCP_REQUEST_BODY_BYTES, create_mcp_http_app
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging import McpAuditIdentityAdapter
from umbod.mcp.middleware import McpAuditMiddleware, McpResponseMetadataMiddleware
from umbod.mcp.middleware.protocol_metrics import McpProtocolMetricsMiddleware
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.telemetry import McpTelemetryDependencies
from umbod.mcp.tools import McpObservedToolRegistrar


async def build_administrator_mcp(
    settings: MCPAppSettings,
    runtime: ConnectorRuntime,
    persistence_runtime: PersistenceRuntime,
    *,
    telemetry: McpTelemetryDependencies,
) -> FastMCP:
    install_umbod_consent_screen()
    signals = create_mcp_signals(
        telemetry.invocation_log_sink, telemetry.metrics_recorder,
        telemetry.audit_recorder, telemetry.application_failures,
    )
    mcp = FastMCP(
        name=f'{settings.runtime.app_name} Administrator',
        version=UMBOD_RELEASE,
        auth=MCPAuthProviderFactory().create_for_base_url(settings, settings.mcp_administrator.base_url),
        middleware=[
            McpResponseMetadataMiddleware(),
            McpProtocolMetricsMiddleware(telemetry.metrics_recorder, clock=time.monotonic),
            McpAuditMiddleware(
                recorder=telemetry.audit_recorder,
                identity_source=McpAuditIdentityAdapter(),
                exposure_mode=settings.mcp.connector_tool_exposure_mode,
            ),
        ],
    )
    await persistence_runtime.readiness.ensure_ready()
    if settings.feature_toggles.mcp_administrator_enabled:
        await register_configured_administrator_tools(
            McpObservedToolRegistrar(mcp, McpInvocationPublisher(signals)),
            settings, runtime, persistence_runtime,
        )
    return mcp


async def build_administrator_app(
    settings: MCPAppSettings,
    runtime: ConnectorRuntime,
    persistence_runtime: PersistenceRuntime,
    *,
    telemetry: McpTelemetryDependencies,
) -> Starlette:
    mcp = await build_administrator_mcp(settings, runtime, persistence_runtime, telemetry=telemetry)
    http_app = create_mcp_http_app(
        mcp, path='/mcp', stateless_http=settings.mcp.stateless_http,
        max_request_body_bytes=MAX_MCP_REQUEST_BODY_BYTES,
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with http_app.lifespan(http_app):
            yield

    async def health_response(_request: Request) -> JSONResponse:
        return JSONResponse({'status': 'ok'})

    return HttpMetadataStarlette(
        routes=[Route('/system/health', health_response, methods=['GET']), Mount('/', app=http_app)],
        lifespan=lifespan,
    )
