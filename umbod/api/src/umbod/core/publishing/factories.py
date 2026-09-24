from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.persistence import Database


class ConfiguredConnectorPublishingStoreFactory:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def __call__(self) -> ConnectorPublishingStore:
        return await create_connector_publishing_store(self._database)


async def create_connector_publishing_store(database: Database) -> ConnectorPublishingStore:
    return ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
