from typing import get_args

from umbod.core.activation.domain import ActivationStatus, CapabilityRef
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CapabilityActivationStateRecord,
)
from umbod.core.invocation import ConnectorKind
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import AllFields, AllOf, OneOf, Query, Unordered

ACTIVATION_READ_BATCH_SIZE = 200


def plan_activation_reads(
    plan: ReadPlanOperations, connector_ids: tuple[str, ...]
) -> tuple[ManyRead[CapabilityActivationStateRecord], ...]:
    identifiers = tuple(sorted(set(connector_ids)))
    return tuple(
        plan.find_many(
            CAPABILITY_ACTIVATION_STATE_TABLE,
            Query(
                filter=AllOf((
                    OneOf(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, get_args(ConnectorKind)),
                    OneOf(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, identifiers[start:start + ACTIVATION_READ_BATCH_SIZE]),
                )),
                projection=AllFields[CapabilityActivationStateRecord](),
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), ACTIVATION_READ_BATCH_SIZE)
    )


class ActivationReadState:
    def __init__(self, rows: tuple[CapabilityActivationStateRecord, ...]) -> None:
        self._statuses = {
            (row.connector_kind, row.connector_id, row.capability_kind, row.capability_key): ActivationStatus(row.status)
            for row in rows
        }

    async def get_status(self, ref: CapabilityRef) -> ActivationStatus:
        return self._statuses.get(
            (ref.connector_kind, ref.connector_id, ref.capability_kind, ref.capability_key),
            ActivationStatus.DISABLED,
        )
