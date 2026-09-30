from umbod.core.administrator.connector_configuration import ConnectorReference
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore


class OpenApiConfigurationCatalog:
    def __init__(self, store: OpenApiConnectorStore) -> None:
        self._store = store

    async def has_connector(self, connector: ConnectorReference) -> bool:
        return connector.connector_kind == "openapi" and any(
            item.connector_id == connector.connector_id
            for item in await self._store.list_connectors()
        )

    async def list_capabilities(
        self, connector: ConnectorReference
    ) -> tuple[CapabilityIdentity, ...]:
        if connector.connector_kind != "openapi":
            return ()
        return tuple(
            CapabilityIdentity(
                connector_kind="openapi",
                connector_id=connector.connector_id,
                capability_kind="tool",
                capability_key=summary.operation_id,
            )
            for summary in await self._store.list_operation_summaries(
                connector.connector_id
            )
        )
