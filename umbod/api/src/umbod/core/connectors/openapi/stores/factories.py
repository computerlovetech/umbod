import asyncio

from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.openapi.stores import (
    CATALOG_OPERATION_TABLE,
    CATALOG_SOURCE_TABLE,
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_TABLE,
    OpenApiConnectorStore,
    OpenApiConnectorStoreService,
)
from umbod.core.persistence import Database

_OPENAPI_TABLES = (
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_TABLE,
    CATALOG_SOURCE_TABLE,
    CATALOG_OPERATION_TABLE,
    CAPABILITY_ACTIVATION_STATE_TABLE,
)


class ConfiguredOpenApiConnectorStoreFactory:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._store: OpenApiConnectorStore | None = None
        self._initialization_lock = asyncio.Lock()

    async def create(self) -> OpenApiConnectorStore:
        async with self._initialization_lock:
            if self._store is None:
                self._store = OpenApiConnectorStoreService(self._database, *_OPENAPI_TABLES)
            return self._store
