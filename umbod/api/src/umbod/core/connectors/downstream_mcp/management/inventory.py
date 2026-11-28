from dataclasses import dataclass

from pydantic import TypeAdapter

from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    ConnectorHealth,
    ToolCatalogSnapshot,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionStore,
    ConnectorHealthFound,
    ConnectorHealthMissing,
)
from umbod.core.connectors.downstream_mcp.stores.reads import (
    plan_overview_catalog_reads,
    plan_overview_health_reads,
)
from umbod.core.persistence import Database
from umbod.core.persistence.plan import ReadPlan
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.publishing.stores.reads import (
    SupportsPlannedPublicationReads,
    plan_publication_reads,
)

_HEALTH_ADAPTER = TypeAdapter(ConnectorHealth)


@dataclass(frozen=True)
class DownstreamConnectorInventoryItem:
    definition: ConnectorDefinition
    icon_url: str
    health: ConnectorHealthFound | ConnectorHealthMissing
    published: bool


class DownstreamConnectorInventoryReader:
    def __init__(
        self, definitions: ConnectorDefinitionStore, database: Database,
        publishing: ConnectorPublishingStore,
    ) -> None:
        self._definitions = definitions
        self._database = database
        self._publishing = publishing

    async def read(self) -> tuple[DownstreamConnectorInventoryItem, ...]:
        definitions = (await self._definitions.list()).definitions
        if not definitions:
            return ()

        connector_ids = tuple(definition.connector_id for definition in definitions)
        plan = ReadPlan()
        catalog_reads = plan_overview_catalog_reads(plan, connector_ids)
        health_reads = plan_overview_health_reads(plan, connector_ids)
        publication_reads = (
            plan_publication_reads(plan, connector_ids)
            if isinstance(self._publishing, SupportsPlannedPublicationReads)
            and self._publishing.can_plan_publication_reads(self._database)
            else ()
        )
        async with self._database.read_session() as session:
            results = await plan.execute(session)

        icons = {
            row.connector_id: _first_icon(ToolCatalogSnapshot.model_validate(row.snapshot))
            for handle in catalog_reads
            for row in results.get(handle)
        }
        health = {
            row.connector_id: ConnectorHealthFound(health=_HEALTH_ADAPTER.validate_python(row.document))
            for handle in health_reads
            for row in results.get(handle)
        }
        if publication_reads:
            published = {
                row.connector_id for handle in publication_reads for row in results.get(handle)
                if row.published
            }
        else:
            published = {
                connector_id for connector_id in connector_ids
                if await self._publishing.is_published(connector_id)
            }
        return tuple(
            DownstreamConnectorInventoryItem(
                definition=definition,
                icon_url=icons.get(definition.connector_id, ""),
                health=health.get(
                    definition.connector_id,
                    ConnectorHealthMissing(connector_id=definition.connector_id),
                ),
                published=definition.connector_id in published,
            )
            for definition in definitions
        )


def _first_icon(snapshot: ToolCatalogSnapshot) -> str:
    return snapshot.server_icons[0].src if snapshot.server_icons else ""
