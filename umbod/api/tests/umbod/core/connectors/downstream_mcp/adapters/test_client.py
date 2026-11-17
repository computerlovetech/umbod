from tests.umbod.core.connectors.downstream_mcp.adapters.credential_fakes import MemoryCredentialStore

import httpx2
import pytest
from pydantic import SecretStr
from fastmcp.client.transports import StreamableHttpTransport

from umbod.core.connectors.downstream_mcp.models import (
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    OAuthConnectorDefinition,
    OAuthCredentialState,
    StaticBearerConnectorDefinition,
    StaticBearerCredentialState,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth_storage import AuthorizationDocument
from umbod.core.connectors.downstream_mcp.oauth.provider import InteractiveConnectorOAuth
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.client import (
    FastMCPDownstreamClientFactory,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPDownstreamConnectionFactory,
)


def test_factory_creates_no_auth_streamable_http_client_with_tls_verification() -> None:
    factory = FastMCPDownstreamClientFactory(
        FastMCPDownstreamConnectionFactory("/tmp/test-ca.pem", MemoryCredentialStore(), oauth_enabled=False)
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


@pytest.mark.asyncio
async def test_factory_creates_oauth_client_with_isolated_auth_and_network_configuration() -> None:
    credentials = MemoryCredentialStore()
    factory = FastMCPDownstreamClientFactory(
        FastMCPDownstreamConnectionFactory(False, credentials, oauth_enabled=True)
    )
    command = DiscoverDownstreamTools(
        definition=OAuthConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
        ),
        credential=OAuthCredentialState(
            connector_id="weather",
            authorization=SecretStr(
                AuthorizationDocument(endpoint_url="https://weather.example/mcp").model_dump_json()
            ),
        ),
    )

    client = factory.create(command)
    transport = client.transport

    assert isinstance(transport, StreamableHttpTransport)
    assert isinstance(transport.auth, InteractiveConnectorOAuth)
    assert transport.auth.storage.connector_id == "weather"
    assert transport.headers == {}
    assert transport.verify is False
    assert transport.httpx_client_factory is not None
    async with transport.httpx_client_factory(follow_redirects=True) as http_client:
        assert http_client.follow_redirects is False
        assert http_client.timeout == httpx2.Timeout(30.0, read=300.0)
    assert credentials.reads == credentials.writes == 0


def test_factory_uses_only_connector_owned_static_bearer_token() -> None:
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True, MemoryCredentialStore(), oauth_enabled=False))
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
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True, MemoryCredentialStore(), oauth_enabled=False))
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
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True, MemoryCredentialStore(), oauth_enabled=False))
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
    factory = FastMCPDownstreamClientFactory(FastMCPDownstreamConnectionFactory(True, MemoryCredentialStore(), oauth_enabled=False))
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
