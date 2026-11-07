from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from umbod.hosting.applications import create_mcp_app, create_rest_app
    from umbod.config.telemetry import TelemetryAppConfig
    from umbod.rest.telemetry.application import create_telemetry_app
    from umbod.hosting.contracts import (
        AccessToken,
        AppConfig,
        ConnectorRegistration,
        InMemoryGroupConnectorToolPermissions,
        JwtClaims,
        JwtVerificationError,
        JwtVerifier,
        MCPAuthProvider,
        McpToolInvocationEvent,
        McpToolInvocationLogSink,
        OAuthService,
        TokenVerifier,
    )

__all__ = [
    "AccessToken",
    "AppConfig",
    "ConnectorRegistration",
    "InMemoryGroupConnectorToolPermissions",
    "JwtClaims",
    "JwtVerificationError",
    "JwtVerifier",
    "MCPAuthProvider",
    "McpToolInvocationEvent",
    "McpToolInvocationLogSink",
    "OAuthService",
    "TokenVerifier",
    "TelemetryAppConfig",
    "create_telemetry_app",
    "create_mcp_app",
    "create_rest_app"
]

_EXPORTS: dict[str, str] = {
    "AccessToken": ".contracts",
    "AppConfig": ".contracts",
    "ConnectorRegistration": ".contracts",
    "InMemoryGroupConnectorToolPermissions": ".contracts",
    "JwtClaims": ".contracts",
    "JwtVerificationError": ".contracts",
    "JwtVerifier": ".contracts",
    "MCPAuthProvider": ".contracts",
    "McpToolInvocationEvent": ".contracts",
    "McpToolInvocationLogSink": ".contracts",
    "OAuthService": ".contracts",
    "TokenVerifier": ".contracts",
    "TelemetryAppConfig": "umbod.config.telemetry",
    "create_telemetry_app": "umbod.rest.telemetry.application",
    "create_mcp_app": ".applications",
    "create_rest_app": ".applications",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
