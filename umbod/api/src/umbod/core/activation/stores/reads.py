from typing import cast, get_args

from pydantic import BaseModel, ConfigDict

from umbod.core.activation.domain import ActivationStatus, CapabilityRef
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
    CAPABILITY_ACTIVATION_STATE_STATUS,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CapabilityActivationStateRecord,
)
from umbod.core.invocation import ConnectorKind
from umbod.core.persistence.plan import ManyRead, ReadPlanOperations
from umbod.core.persistence.query import (
    AllFields, AllOf, AnyOf, Equals, Field, Fields, OneOf, Query, Unordered,
)

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


class EnabledToolReadScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: ConnectorKind
    connector_ids: tuple[str, ...]


class EnabledToolIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: ConnectorKind
    connector_id: str
    capability_key: str


_ENABLED_TOOL_PROJECTION = Fields(
    EnabledToolIdentity,
    cast(
        tuple[Field[CapabilityActivationStateRecord, object], ...],
        (
            CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
            CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
            CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
        ),
    ),
)


def plan_enabled_tool_reads(
    plan: ReadPlanOperations, scopes: tuple[EnabledToolReadScope, ...],
) -> tuple[ManyRead[EnabledToolIdentity], ...]:
    scoped_ids = {
        kind: frozenset(
            identifier for scope in scopes if scope.connector_kind == kind
            for identifier in scope.connector_ids
        )
        for kind in get_args(ConnectorKind)
    }
    identifiers = tuple(sorted(set().union(*scoped_ids.values())))
    return tuple(
        plan.find_many(
            CAPABILITY_ACTIVATION_STATE_TABLE,
            Query(
                filter=AllOf((
                    Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, "tool"),
                    Equals(CAPABILITY_ACTIVATION_STATE_STATUS, "enabled"),
                    AnyOf(tuple(
                        AllOf((
                            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, kind),
                            OneOf(
                                CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
                                tuple(identifier for identifier in batch if identifier in allowed),
                            ),
                        ))
                        for kind, allowed in scoped_ids.items()
                        if allowed.intersection(batch)
                    )),
                )),
                projection=_ENABLED_TOOL_PROJECTION,
                ordering=Unordered(),
            ),
        )
        for start in range(0, len(identifiers), ACTIVATION_READ_BATCH_SIZE)
        for batch in (identifiers[start:start + ACTIVATION_READ_BATCH_SIZE],)
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
