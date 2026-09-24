from datetime import UTC, datetime
from typing import NoReturn

from pydantic import ValidationError

from umbod.core.connectors.downstream_mcp.connection import (
    DownstreamMcpConnectionConfiguration,
    NoAuthConnectionConfiguration,
    OAuthConnectionConfiguration,
    StaticBearerConnectionConfiguration,
    connection_configuration_from_persisted_models,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    ConnectorHealthy,
    CreateConnectorDefinition,
    CredentialState,
    DiscoveredToolWithOutputSchema,
    DiscoveredToolWithoutOutputSchema,
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    OAuthConnectorDefinition,
    OAuthCreateConnectorDefinition,
    OAuthCredentialState,
    PreparedCatalogConnector,
    PreparedConnector,
    StaticBearerConnectorDefinition,
    StaticBearerCreateConnectorDefinition,
    StaticBearerCredentialState,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoveredCapabilityTool,
    DownstreamConnectorValidationError,
    DownstreamConnectorValidationFailed,
    DownstreamMcpProbe,
    ProbeCapabilities,
    ProbeFailed,
    ProbeFailureCode,
)


class DownstreamConnectorPreparation:
    def __init__(self, probe: DownstreamMcpProbe) -> None:
        self._probe = probe

    async def prepare_create(
        self, connector_id: str, request: CreateConnectorDefinition
    ) -> PreparedConnector:
        definition, credential, configuration = self._create_authentication(
            connector_id, request
        )
        result = await self._probe.probe(configuration)
        if isinstance(result, ProbeCapabilities):
            definition = definition.model_copy(update={"endpoint_url": result.endpoint_url})
        return self.catalog_preparation(definition, credential, result)

    async def prepare_update(
        self, definition: ConnectorDefinition, credential: CredentialState
    ) -> PreparedCatalogConnector:
        configuration = connection_configuration_from_persisted_models(
            definition, credential, persist_refresh=False
        )
        result = await self._probe.probe(configuration)
        if isinstance(result, ProbeCapabilities):
            definition = definition.model_copy(update={"endpoint_url": result.endpoint_url})
        return self.catalog_preparation(definition, credential, result)

    def catalog_preparation(
        self, definition: ConnectorDefinition, credential: CredentialState, result: object
    ) -> PreparedCatalogConnector:
        if not isinstance(result, ProbeCapabilities):
            self.raise_probe_failure(result, "auth_rejected")
        checked_at = datetime.now(UTC)
        try:
            snapshot = ToolCatalogSnapshot(
                connector_id=definition.connector_id,
                discovered_at=checked_at,
                tools=tuple(
                    self._bind_tool(definition.connector_id, tool)
                    for tool in result.capabilities.tools
                ),
                server_icons=result.capabilities.server_icons,
                prompts=result.capabilities.prompts,
                resources=result.capabilities.resources,
                resource_templates=result.capabilities.resource_templates,
            )
        except (ValidationError, ValueError):
            raise DownstreamConnectorValidationError(
                DownstreamConnectorValidationFailed(code="invalid_mcp_protocol")
            )
        return PreparedCatalogConnector(
            definition=definition,
            credential=(credential.model_copy(update={"authorization": result.oauth_authorization})
                        if isinstance(credential, OAuthCredentialState) and result.oauth_authorization is not None
                        else credential),
            snapshot=snapshot,
            health=ConnectorHealthy(connector_id=definition.connector_id, checked_at=checked_at),
        )

    def raise_probe_failure(self, result: object, fallback: ProbeFailureCode) -> NoReturn:
        code = result.code if isinstance(result, ProbeFailed) else fallback
        raise DownstreamConnectorValidationError(DownstreamConnectorValidationFailed(code=code))

    @staticmethod
    def _create_authentication(
        connector_id: str, request: CreateConnectorDefinition
    ) -> tuple[
        ConnectorDefinition,
        CredentialState,
        DownstreamMcpConnectionConfiguration,
    ]:
        shared = {
            "connector_id": connector_id,
            "display_name": request.display_name,
            "tool_name_prefix": request.tool_name_prefix,
            "capability_description": request.capability_description,
            "endpoint_url": request.endpoint_url,
            "public_path": request.public_path,
        }
        if isinstance(request, OAuthCreateConnectorDefinition):
            return (
                OAuthConnectorDefinition(**shared),
                OAuthCredentialState(connector_id=connector_id, authorization=request.authorization),
                OAuthConnectionConfiguration(
                    endpoint_url=request.endpoint_url,
                    connector_id=connector_id,
                    authorization=request.authorization,
                    persist_refresh=False,
                ),
            )
        if isinstance(request, StaticBearerCreateConnectorDefinition):
            return (
                StaticBearerConnectorDefinition(
                    **shared,
                    header_type=request.header_type,
                    custom_header_name=request.custom_header_name,
                ),
                StaticBearerCredentialState(
                    connector_id=connector_id,
                    bearer_token=request.bearer_token,
                ),
                StaticBearerConnectionConfiguration(
                    endpoint_url=request.endpoint_url,
                    bearer_token=request.bearer_token,
                    header_type=request.header_type,
                    custom_header_name=request.custom_header_name,
                ),
            )
        return (
            NoAuthConnectorDefinition(**shared),
            NoAuthCredentialState(connector_id=connector_id),
            NoAuthConnectionConfiguration(endpoint_url=request.endpoint_url),
        )

    @staticmethod
    def _bind_tool(
        connector_id: str, tool: DiscoveredCapabilityTool
    ) -> DiscoveredToolWithoutOutputSchema | DiscoveredToolWithOutputSchema:
        shared = tool.model_dump(exclude={"name", "output_schema"})
        shared["identity"] = ToolIdentity(connector_id=connector_id, downstream_name=tool.name)
        if tool.output_schema is None:
            return DiscoveredToolWithoutOutputSchema(**shared)
        return DiscoveredToolWithOutputSchema(**shared, output_schema=tool.output_schema)
