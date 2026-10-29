from typing import Protocol

from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores


class PersonalCatalogueStoreSupplier(Protocol):
    async def create(self) -> DownstreamMcpStores: ...
