from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionList,
    ConnectorDefinitionMissing,
    ConnectorIdQuery,
    PublicPathQuery,
)


class InMemoryConnectorDefinitionReader:
    def __init__(self, definitions: ConnectorDefinitionList) -> None:
        self._definitions = definitions
        self._by_id = {item.connector_id: item for item in definitions.definitions}
        self._by_public_path = {item.public_path: item for item in definitions.definitions}

    async def list(self) -> ConnectorDefinitionList:
        return self._definitions

    async def get(
        self, query: ConnectorIdQuery,
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing:
        definition = self._by_id.get(query.connector_id)
        if definition is None:
            return ConnectorDefinitionMissing(connector_id=query.connector_id)
        return ConnectorDefinitionFound(definition=definition)

    async def get_by_public_path(
        self, query: PublicPathQuery,
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing:
        definition = self._by_public_path.get(query.public_path)
        if definition is None:
            return ConnectorDefinitionMissing(connector_id=query.public_path)
        return ConnectorDefinitionFound(definition=definition)
