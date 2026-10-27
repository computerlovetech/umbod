from umbod.mcp.connectors.downstream_mcp.runtime.catalog import InMemoryDownstreamDiscoveryRuntime
from umbod.mcp.connectors.downstream_mcp.runtime.definitions import DownstreamRuntimeDefinitions
from umbod.mcp.connectors.downstream_mcp.runtime.loader import DownstreamDiscoveryStores, StoreBackedDownstreamDiscoveryLoader
from umbod.mcp.connectors.downstream_mcp.runtime.models import DownstreamDiscoverySnapshot, DownstreamDiscoveryUnavailable
from umbod.mcp.connectors.downstream_mcp.runtime.ports import DownstreamDiscoveryLoader, DownstreamDiscoveryRuntime


def create_downstream_discovery_runtime(stores: DownstreamDiscoveryStores) -> DownstreamDiscoveryRuntime:
    return InMemoryDownstreamDiscoveryRuntime(StoreBackedDownstreamDiscoveryLoader(stores))


__all__ = [
    "DownstreamDiscoveryLoader",
    "DownstreamDiscoveryRuntime",
    "DownstreamDiscoverySnapshot",
    "DownstreamDiscoveryStores",
    "DownstreamDiscoveryUnavailable",
    "DownstreamRuntimeDefinitions",
    "create_downstream_discovery_runtime",
]
