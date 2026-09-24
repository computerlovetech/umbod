import asyncio

from umbod.core.capabilities.descriptions.overrides import (
    ConnectorCapabilityDescriptionOverrideStore,
)
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_TABLE,
)
from umbod.core.capabilities.descriptions.stores.service import (
    ConnectorCapabilityDescriptionOverrideStoreService,
)
from umbod.core.persistence import Database


class ConfiguredConnectorCapabilityDescriptionOverrideStoreFactory:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._store: ConnectorCapabilityDescriptionOverrideStore | None = None
        self._initialization_lock = asyncio.Lock()

    async def create(self) -> ConnectorCapabilityDescriptionOverrideStore:
        async with self._initialization_lock:
            if self._store is None:
                self._store = ConnectorCapabilityDescriptionOverrideStoreService(
                    self._database, CAPABILITY_DESCRIPTION_OVERRIDE_TABLE
                )
            return self._store
