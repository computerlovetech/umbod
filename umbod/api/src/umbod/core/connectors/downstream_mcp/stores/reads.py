from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import AllFields, Field, Fields, NoFilter, OneOf, Query, Unordered

from .schema import (
    CONNECTOR_DEFINITION_CONNECTOR_ID,
    CONNECTOR_DEFINITION_DOCUMENT,
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_CONNECTOR_ID,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_CONNECTOR_ID,
    TOOL_CATALOG_TABLE,
    ConnectorDefinitionRecord,
    ConnectorHealthRecord,
    ToolCatalogRecord,
)


class OverviewDefinitionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: dict[str, object]


_DEFINITION_PROJECTION = Fields(
    OverviewDefinitionRecord,
    cast(
        tuple[Field[ConnectorDefinitionRecord, object], ...],
        (CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_DOCUMENT),
    ),
)


def plan_overview_definition_read(plan: ReadPlanOperations) -> ManyRead[OverviewDefinitionRecord]:
    return plan.find_many(
        CONNECTOR_DEFINITION_TABLE,
        Query(filter=NoFilter(), projection=_DEFINITION_PROJECTION, ordering=Unordered()),
    )


def plan_overview_catalog_reads(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...],
) -> tuple[ManyRead[ToolCatalogRecord], ...]:
    identifiers = tuple(sorted(set(connector_ids)))
    return tuple(
        plan.find_many(
            TOOL_CATALOG_TABLE,
            Query(
                filter=OneOf(TOOL_CATALOG_CONNECTOR_ID, identifiers[start:start + 200]),
                projection=AllFields[ToolCatalogRecord](),
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), 200)
    )


def plan_overview_health_reads(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...],
) -> tuple[ManyRead[ConnectorHealthRecord], ...]:
    identifiers = tuple(sorted(set(connector_ids)))
    return tuple(
        plan.find_many(
            CONNECTOR_HEALTH_TABLE,
            Query(
                filter=OneOf(CONNECTOR_HEALTH_CONNECTOR_ID, identifiers[start:start + 200]),
                projection=AllFields[ConnectorHealthRecord](),
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), 200)
    )
