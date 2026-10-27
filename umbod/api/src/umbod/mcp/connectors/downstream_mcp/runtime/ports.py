from typing import Protocol

from umbod.mcp.connectors.downstream_mcp.runtime.models import DownstreamDiscoverySnapshot


class DownstreamDiscoveryLoader(Protocol):
    async def load(self) -> DownstreamDiscoverySnapshot: ...


class DownstreamDiscoveryRuntime(Protocol):
    def capture(self) -> DownstreamDiscoverySnapshot: ...

    async def reconcile(self) -> None: ...
