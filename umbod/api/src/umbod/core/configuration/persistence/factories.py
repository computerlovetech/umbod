from umbod.core.configuration import EncryptedConnectorConfigurationStoreProtocol
from umbod.core.configuration.persistence.stores.schema import (
    CONNECTOR_CONFIGURATION_TABLE,
)
from umbod.core.configuration.persistence.stores.service import (
    EncryptedConnectorConfigurationStoreService,
)
from umbod.core.persistence import Database


async def create_encrypted_connector_configuration_store(
    database: Database,
) -> EncryptedConnectorConfigurationStoreProtocol:
    return EncryptedConnectorConfigurationStoreService(database, CONNECTOR_CONFIGURATION_TABLE)
