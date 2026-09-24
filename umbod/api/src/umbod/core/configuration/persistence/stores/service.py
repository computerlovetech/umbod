from datetime import UTC, datetime

from umbod.core.configuration.models import EncryptedConnectorConfiguration
from umbod.core.configuration.persistence.stores.schema import (
    CONNECTOR_CONFIGURATION_CONNECTOR_ID,
    CONNECTOR_CONFIGURATION_ID_PROJECTION,
    ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION,
    ConnectorConfigurationKey,
    ConnectorConfigurationRecord,
)
from umbod.core.persistence import (
    TransactionMode,
    Database,
    DeleteQuery,
    Equals,
    Query,
    Table,
    Unordered,
    UpsertCommand,
)


class EncryptedConnectorConfigurationStoreService:
    def __init__(
        self,
        database: Database,
        connector_configurations: Table[ConnectorConfigurationRecord, ConnectorConfigurationKey],
    ) -> None:
        self._database = database
        self._connector_configurations = connector_configurations

    async def save_encrypted_configuration(
        self, configuration: EncryptedConnectorConfiguration
    ) -> None:
        record = ConnectorConfigurationRecord(
            connector_id=configuration.connector_id,
            ciphertext=configuration.ciphertext,
            updated_at=_updated_at(),
        )
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            await session.upsert(
                self._connector_configurations,
                UpsertCommand(
                    key=ConnectorConfigurationKey(connector_id=configuration.connector_id),
                    row=record,
                ),
            )

    async def get_encrypted_configuration(
        self, connector_id: str
    ) -> EncryptedConnectorConfiguration | None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            result = await session.find_one(
                self._connector_configurations,
                Query(
                    filter=Equals(CONNECTOR_CONFIGURATION_CONNECTOR_ID, connector_id),
                    projection=ENCRYPTED_CONNECTOR_CONFIGURATION_PROJECTION,
                    ordering=Unordered(),
                ),
            )
        if result is None:
            return None
        return EncryptedConnectorConfiguration(
            connector_id=result.connector_id,
            ciphertext=result.ciphertext,
        )

    async def count_configurations_for_connector(self, connector_id: str) -> int:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            result = await session.find_one(
                self._connector_configurations,
                Query(
                    filter=Equals(CONNECTOR_CONFIGURATION_CONNECTOR_ID, connector_id),
                    projection=CONNECTOR_CONFIGURATION_ID_PROJECTION,
                    ordering=Unordered(),
                ),
            )
        return 1 if result is not None else 0

    async def delete_encrypted_configuration(self, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            await session.delete(
                self._connector_configurations,
                DeleteQuery(Equals(CONNECTOR_CONFIGURATION_CONNECTOR_ID, connector_id)),
            )


def _updated_at() -> str:
    return datetime.now(UTC).isoformat()
