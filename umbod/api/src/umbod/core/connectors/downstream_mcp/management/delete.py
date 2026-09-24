from umbod.core.publishing.events import connector_publication_changed_event
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.downstream_mcp.errors import DownstreamPermissionGrantConflict
from umbod.core.connectors.downstream_mcp.models import ConnectorDefinition
from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
from umbod.core.connectors.downstream_mcp.management.unit_of_work import (
    DeleteDownstreamConnectorAggregate,
    DownstreamConnectorUnitOfWork,
)
from umbod.core.permissions.ports import GroupPermissionReader
from messaging.ports import EventStream


class DownstreamConnectorDeleter:
    def __init__(
        self,
        permissions: GroupPermissionReader,
        publishing: ConnectorPublishingStore,
        events: EventStream,
        unit_of_work: DownstreamConnectorUnitOfWork,
        queries: DownstreamConnectorQueries,
    ) -> None:
        self._permissions = permissions
        self._publishing = publishing
        self._events = events
        self._unit_of_work = unit_of_work
        self._queries = queries

    async def delete(self, connector_id: str) -> ConnectorDefinition:
        definition = await self._queries.get(connector_id)
        affected_groups = tuple(
            sorted(
                permission_set.group_id
                for permission_set in await self._permissions.list_all_group_permissions()
                if connector_id in permission_set.connector_ids
                or any(tool.connector_id == connector_id for tool in permission_set.tools)
            )
        )
        if affected_groups:
            raise DownstreamPermissionGrantConflict(connector_id, affected_groups)
        was_published = await self._publishing.is_published(connector_id)
        await self._unit_of_work.delete(
            DeleteDownstreamConnectorAggregate(connector_id=connector_id)
        )
        if was_published:
            await self._events.append(
                connector_publication_changed_event(connector_id, "unpublished")
            )
        return definition
