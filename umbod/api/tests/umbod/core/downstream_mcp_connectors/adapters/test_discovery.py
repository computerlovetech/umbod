from datetime import UTC, datetime

import pytest

from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredPrompt,
    DiscoveredResource,
    DiscoveredResourceTemplate,
    DiscoveredServerIcon,
    DiscoveryFailed,
    DiscoverySucceeded,
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    PromptArgument,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoveredCapabilities,
    DiscoveredCapabilityTool,
    ProbeCapabilities,
    ProbeFailed,
    ScriptedDownstreamMcpProbe,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.discovery import (
    FastMCPDownstreamDiscovery,
)


NOW = datetime(2026, 1, 2, tzinfo=UTC)


def _command() -> DiscoverDownstreamTools:
    return DiscoverDownstreamTools(
        definition=NoAuthConnectorDefinition(
            connector_id="weather",
            display_name="Weather",
            endpoint_url="https://weather.example/mcp",
        ),
        credential=NoAuthCredentialState(connector_id="weather"),
    )


def _discovery(capabilities: DiscoveredCapabilities) -> FastMCPDownstreamDiscovery:
    probe = ScriptedDownstreamMcpProbe(
        [ProbeCapabilities(capabilities=capabilities, endpoint_url="https://example.test/mcp")]
    )
    return FastMCPDownstreamDiscovery(probe, timeout_seconds=10.0, clock=lambda: NOW)


def _tool(name: str = "forecast") -> DiscoveredCapabilityTool:
    return DiscoveredCapabilityTool(
        name=name,
        title=name,
        description="Get a forecast",
        input_schema={"type": "object", "required": ["city"]},
    )


@pytest.mark.asyncio
async def test_discover_lists_tools_from_scripted_probe() -> None:
    probe = ScriptedDownstreamMcpProbe(
        [
            ProbeCapabilities(
                capabilities=DiscoveredCapabilities(tools=(_tool(),)),
                endpoint_url="https://example.test/mcp",
            )
        ]
    )
    discovery = FastMCPDownstreamDiscovery(probe, timeout_seconds=10.0, clock=lambda: NOW)

    result = await discovery.discover(_command())

    assert isinstance(result, DiscoverySucceeded)
    assert [tool.identity.downstream_name for tool in result.snapshot.tools] == ["forecast"]
    assert result.snapshot.tools[0].description == "Get a forecast"
    assert result.snapshot.tools[0].input_schema["required"] == ["city"]
    assert probe.commands[0].endpoint_url == "https://weather.example/mcp"
    assert probe.commands[0].connection_type == "none"


@pytest.mark.asyncio
async def test_discover_returns_empty_catalog() -> None:
    result = await _discovery(DiscoveredCapabilities(tools=())).discover(_command())

    assert isinstance(result, DiscoverySucceeded)
    assert result.snapshot.tools == ()


@pytest.mark.asyncio
async def test_discover_preserves_all_tool_metadata() -> None:
    tool = DiscoveredCapabilityTool(
        name="forecast",
        title="Forecast title",
        description="Forecast description",
        input_schema={"type": "object", "x-input": True},
        output_schema={"type": "object", "x-output": True},
        annotations={"title": "Read forecast", "readOnlyHint": True},
        icons=({"src": "https://weather.example/icon.png", "mimeType": "image/png"},),
        meta={"vendor": {"region": "eu"}},
        execution={"taskSupport": "optional"},
    )

    result = await _discovery(DiscoveredCapabilities(tools=(tool,))).discover(_command())

    assert isinstance(result, DiscoverySucceeded)
    discovered = result.snapshot.tools[0]
    assert discovered.title == "Forecast title"
    assert discovered.description == "Forecast description"
    assert discovered.input_schema == {"type": "object", "x-input": True}
    assert discovered.output_schema_status == "present"
    assert discovered.output_schema == {"type": "object", "x-output": True}
    assert discovered.annotations == {"title": "Read forecast", "readOnlyHint": True}
    assert discovered.icons == (
        {"src": "https://weather.example/icon.png", "mimeType": "image/png"},
    )
    assert discovered.meta == {"vendor": {"region": "eu"}}
    assert discovered.execution == {"taskSupport": "optional"}


@pytest.mark.asyncio
async def test_discover_preserves_prompts_resources_and_templates_in_one_snapshot() -> None:
    capabilities = DiscoveredCapabilities(
        tools=(),
        prompts=(
            DiscoveredPrompt(
                name="summarize",
                title="Summarize article",
                description="Create a summary",
                arguments=(
                    PromptArgument(
                        name="article_id", description="Article identifier", required=True
                    ),
                ),
            ),
        ),
        resources=(
            DiscoveredResource(
                name="Guide",
                title="Guide",
                uri="kb://guide",
                description="Knowledge guide",
                mime_type="text/markdown",
            ),
        ),
        resource_templates=(
            DiscoveredResourceTemplate(
                name="Article",
                title="Article",
                uri_template="kb://articles/{article_id}",
                description="Knowledge article",
            ),
        ),
    )

    result = await _discovery(capabilities).discover(_command())

    assert isinstance(result, DiscoverySucceeded)
    assert result.snapshot.prompts[0].arguments[0].required is True
    assert result.snapshot.resources[0].uri == "kb://guide"
    assert result.snapshot.resource_templates[0].uri_template == "kb://articles/{article_id}"


@pytest.mark.asyncio
async def test_discover_preserves_server_icons() -> None:
    capabilities = DiscoveredCapabilities(
        tools=(),
        server_icons=(
            DiscoveredServerIcon(
                src="https://computerlove.tech/icon.png",
                mime_type="image/png",
                sizes=("64x64",),
                theme="light",
            ),
        ),
    )

    result = await _discovery(capabilities).discover(_command())

    assert isinstance(result, DiscoverySucceeded)
    assert result.snapshot.server_icons[0].src == "https://computerlove.tech/icon.png"


@pytest.mark.asyncio
async def test_discover_rejects_duplicate_tool_names() -> None:
    duplicate = _tool("same")

    result = await _discovery(DiscoveredCapabilities(tools=(duplicate, duplicate))).discover(
        _command()
    )

    assert isinstance(result, DiscoveryFailed)
    assert result.reason == "invalid_mcp_protocol"


@pytest.mark.asyncio
async def test_discover_rejects_invalid_tool_schema() -> None:
    invalid = DiscoveredCapabilityTool.model_construct(
        name="invalid",
        title="invalid",
        description="",
        input_schema={"value": float("nan")},
        output_schema=None,
        annotations={},
        icons=(),
        meta={},
        execution={},
    )

    result = await _discovery(DiscoveredCapabilities(tools=(invalid,))).discover(_command())

    assert isinstance(result, DiscoveryFailed)
    assert result.reason == "invalid_mcp_protocol"


@pytest.mark.asyncio
async def test_discover_preserves_sanitized_probe_failure() -> None:
    discovery = FastMCPDownstreamDiscovery(
        ScriptedDownstreamMcpProbe([ProbeFailed(code="unreachable")]),
        timeout_seconds=10.0,
        clock=lambda: NOW,
    )

    result = await discovery.discover(_command())

    assert isinstance(result, DiscoveryFailed)
    assert result.reason == "unreachable"
