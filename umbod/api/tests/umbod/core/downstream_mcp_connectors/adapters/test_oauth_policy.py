import pytest
from pydantic import SecretStr

from umbod.config import OperatorSettings, build_app_config
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPDownstreamConnectionFactory,
)
from umbod.core.connectors.downstream_mcp.adapters.composition import (
    create_downstream_mcp_connections,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import ConnectorOAuth
from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.core.connectors.downstream_mcp.connection import (
    NoAuthConnectionConfiguration,
    OAuthConnectionConfiguration,
    StaticBearerConnectionConfiguration,
)
from umbod.core.connectors.downstream_mcp.models import (
    OAuthConnectorDefinition,
    OAuthCredentialState,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoverDownstreamTools,
    DownstreamConnectorValidationError,
)
from umbod.rest.connectors.downstream_mcp.errors import present_downstream_mcp_error


def connections(enabled: bool = False):
    config = build_app_config(
        OperatorSettings(_env_file=None, mcp_downstream_oauth_enabled=enabled)
    )
    return create_downstream_mcp_connections(
        downstream_mcp_infrastructure_settings_from_app_config(config)
    )


def definition() -> OAuthConnectorDefinition:
    return OAuthConnectorDefinition(
        connector_id="one",
        display_name="OAuth",
        endpoint_url="https://tools.example/mcp",
        tool_name_prefix="oauth",
        capability_description="Test",
        public_path="/mcp/proxies/one",
    )


def credential() -> OAuthCredentialState:
    return OAuthCredentialState(
        connector_id="one", authorization=SecretStr("must-not-be-read")
    )


@pytest.mark.asyncio
async def test_disabled_blocks_probe_runtime_and_background_discovery() -> None:
    bundle = connections()
    command = DiscoverDownstreamTools(definition=definition(), credential=credential())
    with pytest.raises(DownstreamConnectorValidationError) as error:
        bundle.client_factory.create(command)
    assert error.value.code == "oauth_disabled"
    response = present_downstream_mcp_error(error.value)
    assert response.status_code == 403
    assert response.detail["code"] == "oauth_disabled"
    configuration = OAuthConnectionConfiguration(
        endpoint_url=definition().endpoint_url,
        connector_id="one",
        authorization=credential().authorization,
    )
    probe = await bundle.connection.probe(configuration)
    assert probe.code == "oauth_disabled"
    discovery = await bundle.discovery.discover(command)
    assert discovery.reason == "oauth_disabled"


@pytest.mark.parametrize(
    "configuration",
    [
        NoAuthConnectionConfiguration(endpoint_url="https://tools.example/mcp"),
        StaticBearerConnectionConfiguration(
            endpoint_url="https://tools.example/mcp", bearer_token=SecretStr("test")
        ),
    ],
)
def test_disabled_still_constructs_non_oauth_clients(configuration) -> None:
    strategy = FastMCPDownstreamConnectionFactory(True).create(configuration)
    client = strategy.create_client()
    assert client.transport.auth is None
    if configuration.connection_type == "static_bearer":
        assert client.transport.headers["Authorization"] == "Bearer test"


def test_enabled_wires_oauth_into_validation_and_runtime() -> None:
    bundle = connections(True)
    authorization = SecretStr('{"endpoint_url":"https://tools.example/mcp"}')
    configuration = OAuthConnectionConfiguration(
        endpoint_url=definition().endpoint_url,
        connector_id="one",
        authorization=authorization,
    )
    strategy = bundle.client_factory.connection_factory.create(configuration)
    assert isinstance(strategy.create_client().transport.auth, ConnectorOAuth)
    runtime = bundle.client_factory.create(
        DiscoverDownstreamTools(
            definition=definition(),
            credential=OAuthCredentialState(
                connector_id="one", authorization=authorization
            ),
        )
    )
    assert isinstance(runtime.transport.auth, ConnectorOAuth)
