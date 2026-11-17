from dataclasses import dataclass

from umbod.mcp.auth.factory import MCPAuthProvider, MCPAuthProviderFactory
from umbod.mcp.settings import MCPAppSettings


@dataclass(frozen=True)
class AuthenticatedMcpTransport:
    provider: MCPAuthProvider


@dataclass(frozen=True)
class UnauthenticatedMcpTransport:
    pass


McpTransportAuthentication = AuthenticatedMcpTransport | UnauthenticatedMcpTransport


def fastmcp_authentication_provider(authentication: McpTransportAuthentication) -> MCPAuthProvider | None:
    if isinstance(authentication, AuthenticatedMcpTransport):
        return authentication.provider
    if isinstance(authentication, UnauthenticatedMcpTransport):
        return None
    raise TypeError("Explicit MCP transport authentication is required")


def configured_mcp_transport_authentication(settings: MCPAppSettings) -> McpTransportAuthentication:
    provider = MCPAuthProviderFactory().create(settings)
    if provider is None:
        return UnauthenticatedMcpTransport()
    return AuthenticatedMcpTransport(provider)
