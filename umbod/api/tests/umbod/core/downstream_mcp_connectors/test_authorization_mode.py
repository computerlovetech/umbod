import pytest
from pydantic import SecretStr, TypeAdapter, ValidationError

from umbod.core.connectors.downstream_mcp.connection import connection_configuration_from_persisted_models
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    CreateConnectorDefinition,
    OAuthConnectorDefinition,
    OAuthCredentialState,
)
from umbod.rest.connectors.downstream_mcp.schemas import (
    ConnectorConfigurationRequest,
    CreateConnectorConfigurationRequest,
)


@pytest.mark.parametrize("mode", [None, "shared"])
def test_legacy_oauth_definition_preserves_shared_ownership(mode: str | None) -> None:
    document: dict[str, object] = {
        "connector_id": "alpha", "display_name": "Alpha",
        "endpoint_url": "https://alpha.example/mcp", "auth_type": "oauth",
    }
    if mode is not None:
        document["authorization_mode"] = mode
    definition = TypeAdapter(ConnectorDefinition).validate_python(document)
    assert isinstance(definition, OAuthConnectorDefinition)
    assert definition.authorization_mode == "shared"


def test_personal_oauth_definition_cannot_use_shared_credentials() -> None:
    definition = OAuthConnectorDefinition(
        connector_id="alpha", display_name="Alpha", endpoint_url="https://alpha.example/mcp",
        authorization_mode="personal",
    )
    credential = OAuthCredentialState(connector_id="alpha", authorization=SecretStr("admin-canary"))
    with pytest.raises(ValueError, match="Personal OAuth"):
        connection_configuration_from_persisted_models(definition, credential)


def test_shared_creation_contract_rejects_personal_ownership() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(CreateConnectorDefinition).validate_python({
            "display_name": "Alpha", "capability_description": "Alpha capabilities",
            "endpoint_url": "https://alpha.example/mcp", "public_path": "/mcp/proxies/alpha",
            "auth_type": "oauth", "authorization_mode": "personal", "authorization": "admin-canary",
        })


@pytest.mark.parametrize("request_type", [CreateConnectorConfigurationRequest, ConnectorConfigurationRequest])
def test_public_configuration_contract_rejects_personal_oauth(request_type: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(request_type).validate_python({
            "auth_mode": "oauth", "authorization_mode": "personal",
            "endpoint_url": "https://alpha.example/mcp",
        })
