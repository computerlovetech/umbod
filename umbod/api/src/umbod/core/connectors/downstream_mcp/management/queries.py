from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.downstream_mcp.errors import DownstreamConnectorNotFoundError
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    NoAuthConnectorDefinition,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionList,
    ConnectorDefinitionMissing,
    ConnectorDefinitionStore,
    ConnectorHealthFound,
    ConnectorHealthMissing,
    ConnectorHealthStore,
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
    ToolCatalogFound,
    ToolCatalogMissing,
    ToolCatalogStore,
)


class DownstreamConnectorQueries:
    def __init__(
        self,
        definitions: ConnectorDefinitionStore,
        credentials: EncryptedCredentialStore,
        catalogs: ToolCatalogStore,
        health: ConnectorHealthStore,
        publishing: ConnectorPublishingStore,
    ) -> None:
        self._definitions = definitions
        self._credentials = credentials
        self._catalogs = catalogs
        self._health = health
        self._publishing = publishing

    async def list(self) -> ConnectorDefinitionList:
        return await self._definitions.list()

    async def get(self, connector_id: str) -> ConnectorDefinition:
        result = await self._definitions.get(ConnectorIdQuery(connector_id=connector_id))
        if isinstance(result, ConnectorDefinitionMissing):
            raise DownstreamConnectorNotFoundError(connector_id)
        return result.definition

    async def is_published(self, connector_id: str) -> bool:
        return await self._publishing.is_published(connector_id)

    async def credential_configured(self, connector_id: str) -> bool:
        definition = await self.get(connector_id)
        if isinstance(definition, NoAuthConnectorDefinition):
            return False
        result = await self._credentials.get(ConnectorIdQuery(connector_id=connector_id))
        return isinstance(result, CredentialFound)

    async def catalog(self, connector_id: str) -> ToolCatalogFound | ToolCatalogMissing:
        await self.get(connector_id)
        return await self._catalogs.get(ConnectorIdQuery(connector_id=connector_id))

    async def health(self, connector_id: str) -> ConnectorHealthFound | ConnectorHealthMissing:
        await self.get(connector_id)
        return await self._health.get(ConnectorIdQuery(connector_id=connector_id))
