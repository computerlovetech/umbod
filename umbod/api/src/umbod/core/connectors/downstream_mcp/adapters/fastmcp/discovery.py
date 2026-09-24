from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError

from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredToolWithOutputSchema,
    DiscoveredToolWithoutOutputSchema,
    DiscoveryFailed,
    DiscoveryResult,
    DiscoverySucceeded,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoveredCapabilityTool,
    DownstreamMcpProbe,
    ProbeCapabilities,
    ProbeFailed,
)
from umbod.core.connectors.downstream_mcp.connection import connection_configuration_from_persisted_models


class FastMCPDownstreamDiscovery:
    def __init__(self, probe: DownstreamMcpProbe, timeout_seconds: float, clock: Callable[[], datetime]) -> None:
        if timeout_seconds <= 0:
            raise ValueError("discovery timeout must be positive")
        self._probe = probe
        self._clock = clock

    async def discover(self, command: DiscoverDownstreamTools) -> DiscoveryResult:
        attempted_at = self._clock()
        configuration = connection_configuration_from_persisted_models(
            command.definition, command.credential
        )
        result = await self._probe.probe(configuration)
        if isinstance(result, ProbeFailed):
            return DiscoveryFailed(connector_id=command.definition.connector_id, attempted_at=attempted_at, reason=result.code)
        if not isinstance(result, ProbeCapabilities):
            return DiscoveryFailed(connector_id=command.definition.connector_id, attempted_at=attempted_at, reason="auth_rejected")
        try:
            tools = tuple(self._bind_tool(command.definition.connector_id, tool) for tool in result.capabilities.tools)
            snapshot = ToolCatalogSnapshot(
                connector_id=command.definition.connector_id,
                discovered_at=attempted_at,
                tools=tools,
                server_icons=result.capabilities.server_icons,
                prompts=result.capabilities.prompts,
                resources=result.capabilities.resources,
                resource_templates=result.capabilities.resource_templates,
            )
            return DiscoverySucceeded(snapshot=snapshot)
        except (ValidationError, ValueError):
            return DiscoveryFailed(connector_id=command.definition.connector_id, attempted_at=attempted_at, reason="invalid_mcp_protocol")

    @staticmethod
    def _bind_tool(connector_id: str, tool: DiscoveredCapabilityTool) -> DiscoveredToolWithoutOutputSchema | DiscoveredToolWithOutputSchema:
        shared = tool.model_dump(exclude={"name", "output_schema"})
        shared["identity"] = ToolIdentity(connector_id=connector_id, downstream_name=tool.name)
        if tool.output_schema is None:
            return DiscoveredToolWithoutOutputSchema(**shared)
        return DiscoveredToolWithOutputSchema(**shared, output_schema=tool.output_schema)
