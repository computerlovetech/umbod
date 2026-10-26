from umbod.core.connectors.downstream_mcp.connection import DownstreamMcpConnectionConfiguration
from umbod.core.connectors.downstream_mcp.models import DiscoveredServerIcon
from umbod.core.connectors.downstream_mcp.probe import DownstreamMcpProbe, ProbeCapabilities, ProbeResult
from umbod.core.icons import FaviconDiscovery, FaviconDiscoveryRequest, FaviconFound


class FaviconDiscoveringMcpProbe:
    def __init__(self, probe: DownstreamMcpProbe, discovery: FaviconDiscovery) -> None:
        self._probe = probe
        self._discovery = discovery

    async def probe(self, configuration: DownstreamMcpConnectionConfiguration) -> ProbeResult:
        result = await self._probe.probe(configuration)
        if not isinstance(result, ProbeCapabilities) or result.capabilities.server_icons:
            return result
        icon = await self._discovery.discover(
            FaviconDiscoveryRequest(endpoint_url=result.endpoint_url, advertised_icons=()),
        )
        if not isinstance(icon, FaviconFound):
            return result
        return result.model_copy(update={
            "capabilities": result.capabilities.model_copy(update={
                "server_icons": (DiscoveredServerIcon(
                    src=icon.icon.url, mime_type=icon.icon.mime_type, sizes=(), theme="",
                ),),
            }),
        })
