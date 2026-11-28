from uuid import UUID

from umbod.core.persistence import (
    AllFields,
    Database,
    Equals,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)

from .catalog import validate_configuration
from .catalog_models import (
    ManagedConnectorConfiguration,
    ManagedConnectorSummary,
    SavedConfiguration,
    UnsavedConfiguration,
)
from .configuration_schema import pinned_configuration_fields
from .ports import (
    ManagedCatalogUnavailable,
    ManagedConfigurationWriteUnconfirmed,
    ManagedConnectorNotFound,
)
from .schema import (
    CONFIGURATION_CONNECTOR_ID,
    CONNECTOR_ID,
    MANAGED_CATALOG_DETAIL_PROJECTION,
    MANAGED_CATALOG_PROJECTION,
    MANAGED_CONFIGURATION_KEY_PROJECTION,
    MANAGED_CONFIGURATION_TABLE,
    MANAGED_CONNECTOR_TABLE,
    ManagedCatalogRow,
    ManagedConfigurationKey,
    ManagedConfigurationRow,
    ManagedValues,
)


class DatabaseManagedConnectorCatalogStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_connectors(self) -> tuple[ManagedConnectorSummary, ...]:
        try:
            async with self._database.read_session() as session:
                rows = await session.find_many(
                    MANAGED_CONNECTOR_TABLE,
                    Query(NoFilter(), MANAGED_CATALOG_PROJECTION, Unordered()),
                )
                configured = await session.find_many(
                    MANAGED_CONFIGURATION_TABLE,
                    Query(
                        NoFilter(), MANAGED_CONFIGURATION_KEY_PROJECTION, Unordered()
                    ),
                )
                configured_ids = {record.connector_id for record in configured}
                return tuple(
                    _summary(row, row.connector_id in configured_ids)
                    for row in sorted(
                        rows,
                        key=lambda row: (row.display_name.casefold(), row.connector_id),
                    )
                )
        except Exception:
            raise ManagedCatalogUnavailable() from None

    async def read_configuration(
        self, connector_id: UUID
    ) -> ManagedConnectorConfiguration:
        try:
            async with self._database.read_session() as session:
                connector = await session.find_one(
                    MANAGED_CONNECTOR_TABLE,
                    Query(
                        Equals(CONNECTOR_ID, str(connector_id)),
                        MANAGED_CATALOG_DETAIL_PROJECTION,
                        Unordered(),
                    ),
                )
                if connector is None:
                    raise ManagedConnectorNotFound()
                configuration = await session.find_one(
                    MANAGED_CONFIGURATION_TABLE,
                    Query(
                        Equals(CONFIGURATION_CONNECTOR_ID, str(connector_id)),
                        AllFields(),
                        Unordered(),
                    ),
                )
            fields = pinned_configuration_fields(connector.configuration_schema_json)
            return ManagedConnectorConfiguration(
                _summary(connector, configuration is not None),
                fields,
                UnsavedConfiguration.NOT_SAVED
                if configuration is None
                else validate_configuration(fields, configuration.configuration.root),
            )
        except ManagedConnectorNotFound:
            raise
        except Exception:
            raise ManagedCatalogUnavailable() from None

    async def replace_configuration(
        self, connector_id: UUID, configuration: SavedConfiguration
    ) -> None:
        try:
            async with self._database.session(
                mode=TransactionMode.SERIALIZED_WRITE
            ) as session:
                connector = await session.find_one(
                    MANAGED_CONNECTOR_TABLE,
                    Query(
                        Equals(CONNECTOR_ID, str(connector_id)),
                        MANAGED_CATALOG_PROJECTION,
                        Unordered(),
                    ),
                )
                if connector is None:
                    raise ManagedConnectorNotFound()
                await session.upsert(
                    MANAGED_CONFIGURATION_TABLE,
                    UpsertCommand(
                        key=ManagedConfigurationKey(connector_id=str(connector_id)),
                        row=ManagedConfigurationRow(
                            connector_id=str(connector_id),
                            configuration=ManagedValues(configuration.values),
                        ),
                    ),
                )
        except ManagedConnectorNotFound:
            raise
        except Exception:
            raise ManagedConfigurationWriteUnconfirmed() from None


def _summary(row: ManagedCatalogRow, configured: bool) -> ManagedConnectorSummary:
    if row.status != "inactive":
        raise ValueError("Invalid managed connector state")
    return ManagedConnectorSummary(
        UUID(row.connector_id),
        row.display_name,
        row.description,
        "inactive",
        configured,
    )
