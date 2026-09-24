from fastmcp import Client

from umbod.core.connectors.downstream_mcp.connection import (
    connection_configuration_from_persisted_models,
)
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.connection import (
    FastMCPConnectionFactory,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools


class FastMCPDownstreamClientFactory:
    def __init__(self, connection_factory: FastMCPConnectionFactory) -> None:
        self.connection_factory = connection_factory

    def create(self, command: DiscoverDownstreamTools) -> Client:
        configuration = connection_configuration_from_persisted_models(
            command.definition,
            command.credential,
        )
        return self.connection_factory.create(configuration).create_client()
