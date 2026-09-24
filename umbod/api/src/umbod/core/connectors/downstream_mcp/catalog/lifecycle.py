from datetime import UTC, datetime

from umbod.core.configuration.events import connector_configuration_changed_event
from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.downstream_mcp.errors import DownstreamCredentialMissingError
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    ConnectorUnhealthy,
    DiscoveryResult,
    DiscoverySucceeded,
    ToolCatalogSnapshot,
)
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from umbod.core.connectors.downstream_mcp.management.unit_of_work import (
    ApplyDiscoveredCatalog,
    DeleteCatalog,
    DownstreamConnectorUnitOfWork,
    InvalidateDownstreamConnectorAggregate,
)
from umbod.core.connectors.downstream_mcp.probe import (
    DiscoverDownstreamTools,
    DownstreamDiscovery,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorIdQuery,
    CredentialFound,
    EncryptedCredentialStore,
    ToolCatalogFound,
    ToolCatalogStore,
)
from messaging.ports import EventStream


class DownstreamConnectorCatalogLifecycle:
    def __init__(
        self,
        credentials: EncryptedCredentialStore,
        catalogs: ToolCatalogStore,
        discovery: DownstreamDiscovery,
        publishing: ConnectorPublishingStore,
        events: EventStream,
        unit_of_work: DownstreamConnectorUnitOfWork,
        queries: DownstreamConnectorQueries,
    ) -> None:
        self._credentials = credentials
        self._catalogs = catalogs
        self._discovery = discovery
        self._publishing = publishing
        self._events = events
        self._unit_of_work = unit_of_work
        self._queries = queries

    async def refresh(self, connector_id: str) -> DiscoveryResult:
        definition = await self._queries.get(connector_id)
        credential = await self._credentials.get(ConnectorIdQuery(connector_id=connector_id))
        if not isinstance(credential, CredentialFound):
            raise DownstreamCredentialMissingError(connector_id)
        result = await self._discovery.discover(
            DiscoverDownstreamTools(definition=definition, credential=credential.credential)
        )
        catalog, health, operation_names = self._discovery_mutations(connector_id, result)
        await self._unit_of_work.apply_discovery(
            ApplyDiscoveredCatalog(
                connector_id=connector_id,
                catalog=catalog,
                health=health,
                operation_names=operation_names,
            )
        )
        await self._events.append(connector_configuration_changed_event(connector_id))
        return result

    async def invalidate(self, connector_id: str) -> None:
        await self._queries.get(connector_id)
        catalog = await self._catalogs.get(ConnectorIdQuery(connector_id=connector_id))
        was_exposed = await self._publishing.is_published(connector_id) and isinstance(
            catalog, ToolCatalogFound
        )
        await self._unit_of_work.invalidate(
            InvalidateDownstreamConnectorAggregate(
                connector_id=connector_id,
                health=ConnectorUnhealthy(
                    connector_id=connector_id,
                    checked_at=datetime.now(UTC),
                    reason="Rediscovery required after authorization change",
                ),
            )
        )
        if was_exposed:
            await self._events.append(
                connector_publication_changed_event(connector_id, "unpublished")
            )

    @staticmethod
    def _discovery_mutations(
        connector_id: str, result: DiscoveryResult
    ) -> tuple[
        ToolCatalogSnapshot | DeleteCatalog, ConnectorHealthy | ConnectorUnhealthy, tuple[str, ...]
    ]:
        if isinstance(result, DiscoverySucceeded):
            names = tuple(tool.identity.downstream_name for tool in result.snapshot.tools)
            return (
                result.snapshot,
                ConnectorHealthy(
                    connector_id=connector_id, checked_at=result.snapshot.discovered_at
                ),
                names,
            )
        return (
            DeleteCatalog(),
            ConnectorUnhealthy(
                connector_id=connector_id, checked_at=result.attempted_at, reason=result.reason
            ),
            (),
        )
