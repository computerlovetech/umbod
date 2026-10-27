import asyncio

from umbod.mcp.connectors.downstream_mcp.runtime.models import DownstreamDiscoverySnapshot, DownstreamDiscoveryUnavailable
from umbod.mcp.connectors.downstream_mcp.runtime.ports import DownstreamDiscoveryLoader


class InMemoryDownstreamDiscoveryRuntime:
    def __init__(self, loader: DownstreamDiscoveryLoader) -> None:
        self._loader = loader
        self._reconciliation = asyncio.Lock()
        self._state: DownstreamDiscoverySnapshot | DownstreamDiscoveryUnavailable = DownstreamDiscoveryUnavailable()

    def capture(self) -> DownstreamDiscoverySnapshot:
        if isinstance(self._state, DownstreamDiscoveryUnavailable):
            raise DownstreamDiscoveryUnavailable("Downstream discovery is not synchronized")
        return self._state

    async def reconcile(self) -> None:
        async with self._reconciliation:
            try:
                snapshot = await self._loader.load()
            except Exception:
                self._state = DownstreamDiscoveryUnavailable()
                raise
            self._state = snapshot
