from typing import Literal, TypeVar

from pydantic import BaseModel, TypeAdapter

from umbod.core.activation.stores.reads import EnabledToolReadScope, plan_enabled_tool_reads
from umbod.core.configuration.persistence.stores.reads import plan_configuration_presence_reads
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinition,
    ToolCatalogSnapshot,
    uses_personal_oauth,
)
from umbod.core.connectors.downstream_mcp.stores.reads import (
    plan_overview_catalog_reads,
    plan_overview_definition_read,
    plan_overview_health_reads,
)
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.connectors.openapi.stores.reads import (
    plan_connector_inventory_read,
    plan_overview_header_reads,
)
from umbod.core.groups.stores.reads import plan_group_inventory_read
from umbod.core.persistence import Database, TransactionMode
from umbod.core.persistence.plan import ManyRead, ReadPlan, ReadResults
from umbod.core.publishing.stores.reads import plan_publication_reads

from umbod.core.admin_overview.models import (
    Available, ConnectorCounts, OverviewBreakdown, OverviewSnapshot, ToolCounts,
)

RowT = TypeVar("RowT", bound=BaseModel)
ToolKey = tuple[str, str, str]


class DatabaseOverviewReader:
    def __init__(self, database: Database, registry: ConnectorRegistry) -> None:
        self._database = database
        self._registry = registry

    async def read(self) -> OverviewSnapshot:
        definitions = self._registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="available")
        )
        native_ids = tuple(definition.metadata.id for definition in definitions)
        native_tools = frozenset(
            ("native", definition.metadata.id, tool.operation_name)
            for definition in definitions
            for tool in definition.tool_descriptions.values()
        )
        inventory = ReadPlan()
        openapi_inventory = plan_connector_inventory_read(inventory)
        downstream_inventory = plan_overview_definition_read(inventory)
        groups = plan_group_inventory_read(inventory)
        configurations = plan_configuration_presence_reads(inventory, native_ids)
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            initial = await inventory.execute(session)
            openapi_ids = tuple(row.connector_id for row in initial.get(openapi_inventory))
            definition_adapter = TypeAdapter(ConnectorDefinition)
            shared_ids = tuple(
                row.connector_id
                for row in initial.get(downstream_inventory)
                if not uses_personal_oauth(definition_adapter.validate_python(row.document))
            )
            state = ReadPlan()
            headers = plan_overview_header_reads(state, openapi_ids)
            catalogs = plan_overview_catalog_reads(state, shared_ids)
            health = plan_overview_health_reads(state, shared_ids)
            identifiers = native_ids + openapi_ids + shared_ids
            publications = plan_publication_reads(state, identifiers)
            activations = plan_enabled_tool_reads(state, (
                EnabledToolReadScope(connector_kind="native", connector_ids=native_ids),
                EnabledToolReadScope(connector_kind="openapi", connector_ids=openapi_ids),
                EnabledToolReadScope(connector_kind="downstream_mcp", connector_ids=shared_ids),
            ))
            results = await state.execute(session)
        published = frozenset(
            row.connector_id for row in _rows(results, publications) if row.published
        )
        previous = frozenset(
            row.connector_id for row in _rows(results, publications) if row.previously_published
        )
        enabled = frozenset(
            (row.connector_kind, row.connector_id, row.capability_key)
            for row in _rows(results, activations)
        )
        configured = frozenset(row.connector_id for row in _rows(initial, configurations))
        openapi_tools = frozenset(
            ("openapi", row.connector_id, operation_id)
            for row in _rows(results, headers)
            for operation_id in row.operation_ids
        )
        downstream_tools = frozenset(
            ("downstream_mcp", row.connector_id, tool.identity.downstream_name)
            for row in _rows(results, catalogs)
            for tool in ToolCatalogSnapshot.model_validate(row.snapshot).tools
        )
        unhealthy = frozenset(
            row.connector_id for row in _rows(results, health)
            if row.document.get("status") == "unhealthy"
        )
        return OverviewSnapshot(
            breakdown=(
                _family("catalog", native_ids, configured, published, previous, frozenset(), native_tools, enabled),
                _family(
                    "openapi", openapi_ids,
                    frozenset(row.connector_id for row in _rows(results, headers)),
                    published, previous, frozenset(), openapi_tools, enabled,
                ),
                _family(
                    "mcp", shared_ids, frozenset(shared_ids), published, previous,
                    unhealthy, downstream_tools, enabled,
                ),
            ),
            permission_groups=Available(
                status="available",
                value=sum(bool(row.group_id.strip()) for row in initial.get(groups)),
            ),
        )


def _rows(results: ReadResults, handles: tuple[ManyRead[RowT], ...]) -> tuple[RowT, ...]:
    return tuple(row for handle in handles for row in results.get(handle))


def _family(
    kind: Literal["catalog", "openapi", "mcp"],
    connector_ids: tuple[str, ...],
    configured: frozenset[str],
    published: frozenset[str],
    previous: frozenset[str],
    unhealthy: frozenset[str],
    known_tools: frozenset[ToolKey],
    enabled_tools: frozenset[ToolKey],
) -> OverviewBreakdown:
    identifiers = frozenset(connector_ids)
    not_published = identifiers - published
    unpublished = not_published if kind == "mcp" else not_published & previous
    draft = frozenset() if kind == "mcp" else (not_published - previous) & configured
    unconfigured = frozenset() if kind == "mcp" else not_published - previous - configured
    return OverviewBreakdown(
        kind=kind,
        connectors=Available(
            status="available",
            value=ConnectorCounts(
                configured=len(identifiers) - len(unconfigured),
                published=len(identifiers & published),
                unconfigured=len(unconfigured),
                draft=len(draft),
                unpublished=len(unpublished),
                unhealthy=len(identifiers & unhealthy),
            ),
        ),
        tools=Available(
            status="available",
            value=ToolCounts(known=len(known_tools), enabled=len(known_tools & enabled_tools)),
        ),
    )
