from typing import Annotated, Literal, Union
from pydantic import Field, SecretStr

from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    CredentialState,
    DomainModel,
    EndpointUrl,
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    OAuthConnectorDefinition,
    OAuthCredentialState,
    StaticBearerConnectorDefinition,
    StaticBearerCredentialState,
    StaticTokenHeaderType,
)


class NoAuthConnectionConfiguration(DomainModel):
    connection_type: Literal["none"] = "none"
    endpoint_url: EndpointUrl


class StaticBearerConnectionConfiguration(DomainModel):
    connection_type: Literal["static_bearer"] = "static_bearer"
    endpoint_url: EndpointUrl
    bearer_token: SecretStr
    header_type: StaticTokenHeaderType = "bearer"
    custom_header_name: str | None = None


class OAuthConnectionConfiguration(DomainModel):
    connection_type: Literal["oauth"] = "oauth"
    endpoint_url: EndpointUrl
    connector_id: str
    authorization: SecretStr
    persist_refresh: bool = True


DownstreamMcpConnectionConfiguration = Annotated[
    Union[
        NoAuthConnectionConfiguration,
        StaticBearerConnectionConfiguration,
        OAuthConnectionConfiguration,
    ],
    Field(discriminator="connection_type"),
]


def connection_configuration_from_persisted_models(
    definition: ConnectorDefinition,
    credential: CredentialState,
    *,
    persist_refresh: bool = True,
) -> DownstreamMcpConnectionConfiguration:
    if definition.connector_id != credential.connector_id:
        raise ValueError("connector credential does not match definition")
    if isinstance(definition, NoAuthConnectorDefinition) and isinstance(
        credential, NoAuthCredentialState
    ):
        return NoAuthConnectionConfiguration(endpoint_url=definition.endpoint_url)
    if isinstance(definition, StaticBearerConnectorDefinition) and isinstance(
        credential, StaticBearerCredentialState
    ):
        return StaticBearerConnectionConfiguration(
            endpoint_url=definition.endpoint_url,
            bearer_token=credential.bearer_token,
            header_type=definition.header_type,
            custom_header_name=definition.custom_header_name,
        )
    if isinstance(definition, OAuthConnectorDefinition) and isinstance(
        credential, OAuthCredentialState
    ):
        return OAuthConnectionConfiguration(
            endpoint_url=definition.endpoint_url,
            connector_id=definition.connector_id,
            authorization=credential.authorization,
            persist_refresh=persist_refresh,
        )
    raise ValueError("connector authentication configuration does not match credential")
