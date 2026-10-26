from typing import cast

import pytest

from umbod.core.connectors.downstream_mcp.adapters.icon_discovery import FaviconDiscoveringMcpProbe
from umbod.core.connectors.downstream_mcp.connection import NoAuthConnectionConfiguration
from umbod.core.connectors.downstream_mcp.models import DiscoveredServerIcon
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoveredCapabilities,
    DownstreamMcpProbe,
    ProbeCapabilities,
    ProbeFailed,
    ScriptedDownstreamMcpProbe,
)
from umbod.core.icons import (
    Favicon,
    FaviconDiscoveryRequest,
    FaviconDiscoveryResult,
    FaviconDiscoveryTimedOut,
    FaviconFound,
    FaviconNotFound,
)


class RecordingFaviconDiscovery:
    def __init__(self, result: FaviconDiscoveryResult) -> None:
        self.result = result
        self.requests: list[FaviconDiscoveryRequest] = []

    async def discover(self, request: FaviconDiscoveryRequest) -> FaviconDiscoveryResult:
        self.requests.append(request)
        return self.result


def _capabilities(icons: tuple[DiscoveredServerIcon, ...]) -> ProbeCapabilities:
    return ProbeCapabilities(
        endpoint_url="https://canonical.example/mcp",
        capabilities=DiscoveredCapabilities(tools=(), server_icons=icons),
    )


@pytest.mark.asyncio
async def test_missing_mcp_icons_are_discovered_at_canonical_endpoint() -> None:
    discovery = RecordingFaviconDiscovery(FaviconFound(
        icon=Favicon(url="https://canonical.example/favicon.ico", mime_type="image/x-icon"),
        strategy="origin_favicon",
    ))
    probe: DownstreamMcpProbe = FaviconDiscoveringMcpProbe(
        ScriptedDownstreamMcpProbe((_capabilities(()),)), discovery,
    )
    result = await probe.probe(NoAuthConnectionConfiguration(endpoint_url="https://original.example/mcp"))
    assert isinstance(result, ProbeCapabilities)
    assert result.capabilities.server_icons == (DiscoveredServerIcon(
        src="https://canonical.example/favicon.ico", mime_type="image/x-icon", sizes=(), theme="",
    ),)
    assert str(discovery.requests[0].endpoint_url) == "https://canonical.example/mcp"


@pytest.mark.asyncio
async def test_advertised_mcp_icons_skip_public_discovery_and_preserve_metadata() -> None:
    icon = DiscoveredServerIcon(src="data:image/png;base64,aGVsbG8=", mime_type="image/png", sizes=("48x48",), theme="dark")
    original = _capabilities((icon,))
    discovery = RecordingFaviconDiscovery(FaviconNotFound())
    probe: DownstreamMcpProbe = FaviconDiscoveringMcpProbe(ScriptedDownstreamMcpProbe((original,)), discovery)
    result = await probe.probe(NoAuthConnectionConfiguration(endpoint_url="https://original.example/mcp"))
    assert result is original
    assert discovery.requests == []


@pytest.mark.asyncio
async def test_failed_mcp_probe_does_not_start_icon_discovery() -> None:
    original = ProbeFailed(code="auth_rejected")
    discovery = RecordingFaviconDiscovery(FaviconNotFound())
    probe: DownstreamMcpProbe = FaviconDiscoveringMcpProbe(ScriptedDownstreamMcpProbe((original,)), discovery)
    result = await probe.probe(NoAuthConnectionConfiguration(endpoint_url="https://original.example/mcp"))
    assert result is original
    assert discovery.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [FaviconNotFound(), FaviconDiscoveryTimedOut()])
async def test_unsuccessful_icon_discovery_preserves_successful_probe(outcome: FaviconDiscoveryResult) -> None:
    original = _capabilities(())
    probe: DownstreamMcpProbe = FaviconDiscoveringMcpProbe(
        ScriptedDownstreamMcpProbe((original,)), RecordingFaviconDiscovery(outcome),
    )
    result = await probe.probe(NoAuthConnectionConfiguration(endpoint_url="https://original.example/mcp"))
    assert cast(ProbeCapabilities, result) is original
