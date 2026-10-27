from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import AllFields, OneOf, Query, Unordered
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_TABLE,
    PublicationStateRecord,
)

PUBLICATION_READ_BATCH_SIZE = 200


def plan_publication_reads(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...]
) -> tuple[ManyRead[PublicationStateRecord], ...]:
    identifiers = tuple(sorted(set(connector_ids)))
    return tuple(
        plan.find_many(
            PUBLICATION_STATE_TABLE,
            Query(
                filter=OneOf(PUBLICATION_STATE_CONNECTOR_ID, identifiers[start:start + PUBLICATION_READ_BATCH_SIZE]),
                projection=AllFields[PublicationStateRecord](),
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), PUBLICATION_READ_BATCH_SIZE)
    )


class PublicationReadState:
    def __init__(self, rows: tuple[PublicationStateRecord, ...]) -> None:
        self._published = frozenset(row.connector_id for row in rows if row.published)
        self._previously_published = frozenset(
            row.connector_id for row in rows if row.previously_published
        )

    async def is_published(self, connector_id: str) -> bool:
        return connector_id in self._published

    async def was_previously_published(self, connector_id: str) -> bool:
        return connector_id in self._previously_published
