from umbod.core.connectors.downstream_mcp.adapters.composition import create_downstream_mcp_connections
from umbod.core.connectors.downstream_mcp.adapters.settings import DownstreamMcpInfrastructureSettings


def infrastructure_settings() -> DownstreamMcpInfrastructureSettings:
    return DownstreamMcpInfrastructureSettings(
        credential_secret="test-credential-secret",
        tls_verification=True,
        connection_timeout_seconds=10.0,
        discovery_timeout_seconds=17.0,
    )


def test_connections_use_explicit_network_configuration() -> None:
    settings = infrastructure_settings()
    connections = create_downstream_mcp_connections(settings)

    assert settings.discovery_timeout_seconds == 17.0
    assert connections.discovery is not None
    assert (
        connections.connection.connection_factory
        is connections.client_factory.connection_factory
    )


def test_connections_create_request_owned_bundles() -> None:
    settings = infrastructure_settings()
    first_connections = create_downstream_mcp_connections(settings)
    second_connections = create_downstream_mcp_connections(settings)

    assert first_connections is not second_connections
    assert first_connections.connection is not second_connections.connection
