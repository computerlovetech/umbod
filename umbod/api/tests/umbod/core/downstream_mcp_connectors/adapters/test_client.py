import pytest
from fastmcp.client.transports import StreamableHttpTransport

from umbod.core.connectors.downstream_mcp.models import (
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    StaticBearerConnectorDefinition,
    StaticBearerCredentialState,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.client import (
    FastMCPDownstreamClientFactory,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPDownstreamConnectionFactory,
)


def test_factory_creates_no_auth_streamable_http_client_with_tls_verification() -> None:
    factory = FastMCPDownstreamClientFactory(
        FastMCPDownstreamConnectionFactory("/tmp/test-ca.pem")
    )
    command = DiscoverDownstreamTools(
        definition=NoAuthConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
        ),
        credential=NoAuthCredentialState(connector_id="weather"),
    )

    client = factory.create(command)

    assert isinstance(client.transport, StreamableHttpTransport)
    assert client.transport.verify == "/tmp/test-ca.pem"
    assert client.transport.auth is None
    assert client.transport.headers == {}


def test_factory_uses_only_connector_owned_static_bearer_token() -> None:
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True))
    command = DiscoverDownstreamTools(
        definition=StaticBearerConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
        ),
        credential=StaticBearerCredentialState(
            connector_id="weather",
            bearer_token="connector-secret",
        ),
    )

    client = factory.create(command)

    assert isinstance(client.transport, StreamableHttpTransport)
    assert client.transport.auth is None
    assert client.transport.headers == {"Authorization": "Bearer connector-secret"}


def test_factory_sends_basic_token_without_transformation() -> None:
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True))
    command = DiscoverDownstreamTools(
        definition=StaticBearerConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
            header_type="basic",
        ),
        credential=StaticBearerCredentialState(
            connector_id="weather",
            bearer_token="already-encoded",
        ),
    )

    client = factory.create(command)

    assert client.transport.headers == {"Authorization": "Basic already-encoded"}


def test_factory_rejects_definition_credential_authentication_mismatch() -> None:
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True))
    command = DiscoverDownstreamTools(
        definition=NoAuthConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
        ),
        credential=StaticBearerCredentialState(
            connector_id="weather",
            bearer_token="connector-secret",
        ),
    )

    with pytest.raises(
        ValueError,
        match="connector authentication configuration does not match credential",
    ):
        factory.create(command)


def test_factory_sends_custom_token_unchanged() -> None:
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True))
    command = DiscoverDownstreamTools(
        definition=StaticBearerConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
            header_type="custom",
            custom_header_name="X-Api-Key",
        ),
        credential=StaticBearerCredentialState(
            connector_id="weather",
            bearer_token="connector-secret",
        ),
    )

    client = factory.create(command)

    assert client.transport.headers == {"X-Api-Key": "connector-secret"}
