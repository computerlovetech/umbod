from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import OneOf, Query, Unordered

from .schema import (
    CONNECTOR_CONFIGURATION_CONNECTOR_ID,
    CONNECTOR_CONFIGURATION_ID_PROJECTION,
    CONNECTOR_CONFIGURATION_TABLE,
    ConnectorConfigurationIdResult,
)


def plan_configuration_presence_reads(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...],
) -> tuple[ManyRead[ConnectorConfigurationIdResult], ...]:
    identifiers = tuple(sorted(set(connector_ids)))
    return tuple(
        plan.find_many(
            CONNECTOR_CONFIGURATION_TABLE,
            Query(
                filter=OneOf(CONNECTOR_CONFIGURATION_CONNECTOR_ID, identifiers[start:start + 200]),
                projection=CONNECTOR_CONFIGURATION_ID_PROJECTION,
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), 200)
    )
