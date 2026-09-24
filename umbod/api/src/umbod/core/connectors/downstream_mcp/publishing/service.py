from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolIdentitySource, PublicToolNameValidator
from umbod.core.connectors.downstream_mcp.errors import DownstreamConnectorUnavailableError
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from umbod.core.connectors.downstream_mcp.stores.ports import ToolCatalogFound
from messaging.ports import EventStream


class DownstreamConnectorPublisher:
    def __init__(
        self,
        publishing: ConnectorPublishingStore,
        events: EventStream,
        queries: DownstreamConnectorQueries,
        tool_name_validator: PublicToolNameValidator,
        identity_source: PublicToolIdentitySource,
    ) -> None:
        self._publishing = publishing
        self._events = events
        self._queries = queries
        self._tool_name_validator = tool_name_validator
        self._identity_source = identity_source

    async def publish(self, connector_id: str) -> None:
        catalog = await self._queries.catalog(connector_id)
        if not isinstance(catalog, ToolCatalogFound) or not any(
            (
                catalog.snapshot.tools,
                catalog.snapshot.prompts,
                catalog.snapshot.resources,
                catalog.snapshot.resource_templates,
            )
        ):
            raise DownstreamConnectorUnavailableError(connector_id)
        self._tool_name_validator.validate_unique(await self._public_identities(connector_id))
        if not await self._publishing.is_published(connector_id):
            await self._publishing.publish_connector(connector_id)
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

    async def _public_identities(self, connector_id: str) -> tuple[PublicToolIdentity, ...]:
        identities = list(await self._identity_source.identities())
        for definition in (await self._queries.list()).definitions:
            if definition.connector_id != connector_id and not await self._publishing.is_published(
                definition.connector_id
            ):
                continue
            catalog = await self._queries.catalog(definition.connector_id)
            if isinstance(catalog, ToolCatalogFound):
                identities.extend(
                    PublicToolIdentity(
                        connector_id=tool.identity.connector_id,
                        tool_name_prefix=definition.tool_name_prefix,
                        operation_name=tool.identity.downstream_name,
                    )
                    for tool in catalog.snapshot.tools
                )
        return tuple(identities)
