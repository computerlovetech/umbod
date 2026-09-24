from collections.abc import Sequence
from typing import Annotated, Literal, Protocol, Union

from pydantic import Field, SecretStr, TypeAdapter

from umbod.core.connectors.downstream_mcp.connection import DownstreamMcpConnectionConfiguration

from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    CredentialState,
    DiscoveredPrompt,
    DiscoveredResource,
    DiscoveredResourceTemplate,
    DiscoveredServerIcon,
    DiscoveryResult,
    DomainModel,
    EndpointUrl,
    ValidatedJsonObject,
)

DISCOVERY_RESULT_ADAPTER = TypeAdapter(DiscoveryResult)


class DiscoverDownstreamTools(DomainModel):
    definition: ConnectorDefinition
    credential: CredentialState


class DownstreamDiscovery(Protocol):
    async def discover(self, command: DiscoverDownstreamTools) -> DiscoveryResult: ...



ProbeFailureCode = Literal[
    "oauth_disabled",
    "endpoint_not_found",
    "auth_rejected",
    "unreachable",
    "timeout",
    "invalid_mcp_protocol",
    "unsafe_redirect",
    "redirect_limit_exceeded",
]


class DiscoveredCapabilityTool(DomainModel):
    name: str
    title: str
    description: str
    input_schema: ValidatedJsonObject
    output_schema: ValidatedJsonObject | None = None
    annotations: ValidatedJsonObject = Field(default_factory=dict)
    icons: tuple[ValidatedJsonObject, ...] = ()
    meta: ValidatedJsonObject = Field(default_factory=dict)
    execution: ValidatedJsonObject = Field(default_factory=dict)


class DiscoveredCapabilities(DomainModel):
    tools: tuple[DiscoveredCapabilityTool, ...]
    server_icons: tuple[DiscoveredServerIcon, ...] = ()
    prompts: tuple[DiscoveredPrompt, ...] = ()
    resources: tuple[DiscoveredResource, ...] = ()
    resource_templates: tuple[DiscoveredResourceTemplate, ...] = ()


class ProbeCapabilities(DomainModel):
    status: Literal["capabilities"] = "capabilities"
    capabilities: DiscoveredCapabilities
    endpoint_url: EndpointUrl
    oauth_authorization: SecretStr | None = None


class ProbeFailed(DomainModel):
    status: Literal["failed"] = "failed"
    code: ProbeFailureCode


ProbeResult = Annotated[
    Union[ProbeCapabilities, ProbeFailed], Field(discriminator="status")
]


class DownstreamMcpProbe(Protocol):
    async def probe(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> ProbeResult: ...


class ScriptedDownstreamMcpProbe:
    def __init__(self, results: Sequence[ProbeResult]) -> None:
        self._results = list(results)
        self.commands: list[DownstreamMcpConnectionConfiguration] = []

    async def probe(
        self, configuration: DownstreamMcpConnectionConfiguration
    ) -> ProbeResult:
        self.commands.append(configuration)
        if not self._results:
            raise RuntimeError("No scripted downstream MCP probe result")
        return self._results.pop(0)
