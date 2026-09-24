from dataclasses import dataclass
from umbod.core.connectors.downstream_mcp.stores.ports import EncryptedCredentialStore
from datetime import UTC, datetime

from umbod.core.connectors.downstream_mcp.probe import DownstreamMcpProbe
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.client import FastMCPDownstreamClientFactory
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import FastMCPDownstreamConnectionFactory
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.discovery import FastMCPDownstreamDiscovery
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.probe import FastMCPDownstreamConnection
from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings


@dataclass(frozen=True)
class DownstreamMcpConnections:
    connection: FastMCPDownstreamConnection
    client_factory: FastMCPDownstreamClientFactory
    discovery: FastMCPDownstreamDiscovery


def create_downstream_mcp_connections(
    settings: DownstreamMcpInfrastructureSettings,
    credentials: EncryptedCredentialStore | None = None,
) -> DownstreamMcpConnections:
    connection_factory = FastMCPDownstreamConnectionFactory(
        settings.tls_verification,
        credentials,
        oauth_enabled=settings.oauth_enabled,
    )
    connection = FastMCPDownstreamConnection(
        settings.tls_verification,
        settings.connection_timeout_seconds,
        connection_factory,
    )
    client_factory = FastMCPDownstreamClientFactory(connection_factory)
    discovery = create_downstream_mcp_discovery(settings, connection)
    return DownstreamMcpConnections(
        connection=connection,
        client_factory=client_factory,
        discovery=discovery,
    )


def create_downstream_mcp_discovery(
    settings: DownstreamMcpInfrastructureSettings,
    probe: DownstreamMcpProbe,
) -> FastMCPDownstreamDiscovery:
    return FastMCPDownstreamDiscovery(
        probe,
        timeout_seconds=settings.discovery_timeout_seconds,
        clock=lambda: datetime.now(UTC),
    )
