from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionList
from umbod.mcp.connectors.downstream_mcp.runtime.ports import DownstreamDiscoveryRuntime


class DownstreamRuntimeDefinitions:
    def __init__(self, runtime: DownstreamDiscoveryRuntime) -> None:
        self._runtime = runtime

    async def list(self) -> ConnectorDefinitionList:
        return ConnectorDefinitionList(definitions=self._runtime.capture().definitions)
