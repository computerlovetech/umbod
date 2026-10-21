from typing import Protocol

from fastmcp import Client

from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools


class DownstreamClientFactory(Protocol):
    def create(self, command: DiscoverDownstreamTools) -> Client: ...


__all__ = ["DownstreamClientFactory"]
