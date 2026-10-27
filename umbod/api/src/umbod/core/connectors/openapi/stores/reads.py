from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import Field, Fields, NoFilter, OneOf, Query, Unordered

from .schema import (
    CONNECTOR_ID,
    CONNECTOR_TABLE,
    CURRENT_CATALOG_HEADER_CONNECTOR_ID,
    CURRENT_CATALOG_HEADER_OPERATION_IDS,
    CURRENT_CATALOG_HEADER_TABLE,
    ConnectorKey,
    ConnectorRecord,
    CurrentCatalogHeaderRecord,
)


class OverviewCatalogHeader(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    operation_ids: tuple[str, ...]


_CONNECTOR_ID_PROJECTION = Fields(
    ConnectorKey, cast(tuple[Field[ConnectorRecord, object], ...], (CONNECTOR_ID,)),
)
_HEADER_PROJECTION = Fields(
    OverviewCatalogHeader,
    cast(
        tuple[Field[CurrentCatalogHeaderRecord, object], ...],
        (CURRENT_CATALOG_HEADER_CONNECTOR_ID, CURRENT_CATALOG_HEADER_OPERATION_IDS),
    ),
)


def plan_connector_inventory_read(plan: ReadPlanOperations) -> ManyRead[ConnectorKey]:
    return plan.find_many(
        CONNECTOR_TABLE,
        Query(filter=NoFilter(), projection=_CONNECTOR_ID_PROJECTION, ordering=Unordered()),
    )


def plan_overview_header_reads(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...],
) -> tuple[ManyRead[OverviewCatalogHeader], ...]:
    identifiers = tuple(sorted(set(connector_ids)))
    return tuple(
        plan.find_many(
            CURRENT_CATALOG_HEADER_TABLE,
            Query(
                filter=OneOf(CURRENT_CATALOG_HEADER_CONNECTOR_ID, identifiers[start:start + 200]),
                projection=_HEADER_PROJECTION,
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), 200)
    )
