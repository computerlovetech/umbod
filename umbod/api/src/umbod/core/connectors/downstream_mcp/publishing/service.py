from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolIdentitySource
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from umbod.core.connectors.downstream_mcp.management.unit_of_work import DownstreamConnectorUnitOfWork, PublishDownstreamConnectorAggregate
from messaging.ports import EventStream


class DownstreamConnectorPublisher:
    def __init__(
        self,
        publishing: ConnectorPublishingStore,
        events: EventStream,
        queries: DownstreamConnectorQueries,
        unit_of_work: DownstreamConnectorUnitOfWork,
        identity_source: PublicToolIdentitySource,
    ) -> None:
        self._publishing = publishing
        self._events = events
        self._queries = queries
        self._unit_of_work = unit_of_work
        self._identity_source = identity_source

    async def publish(self, connector_id: str) -> None:
        changed = await self._unit_of_work.publish(PublishDownstreamConnectorAggregate(
            connector_id=connector_id,
            native_identities=await self._identity_source.identities(),
        ))
        if changed:
            await self._events.append(
                connector_publication_changed_event(connector_id, "published")
            )

    async def unpublish(self, connector_id: str) -> None:
        await self._queries.get(connector_id)
        if await self._publishing.is_published(connector_id):
            await self._publishing.unpublish_connector(connector_id)
            await self._events.append(
                connector_publication_changed_event(connector_id, "unpublished")
            )
