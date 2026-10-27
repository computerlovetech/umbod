from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.messaging.discovery_events import connector_discovery_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session
from datetime import UTC, datetime

from umbod.core.activation.domain import (
    ActivationStatus,
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.core.activation.stores.schema import (
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID,
    CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND,
    CAPABILITY_ACTIVATION_STATE_TABLE,
    CAPABILITY_ACTIVATION_STATUS_PROJECTION,
    CapabilityActivationStateKey,
    CapabilityActivationStateRecord,
)
from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.invocation import ConnectorKind
from umbod.core.persistence import (
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Not,
    OneOf,
    Query,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


async def get_status_in_session(
    session: DatabaseSession,
    ref: CapabilityRef,
) -> ActivationStatus:
    result = await session.find_one(
        CAPABILITY_ACTIVATION_STATE_TABLE,
        Query(
            filter=AllOf(
                (
                    Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, ref.connector_kind),
                    Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, ref.connector_id),
                    Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, ref.capability_kind),
                    Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY, ref.capability_key),
                )
            ),
            projection=CAPABILITY_ACTIVATION_STATUS_PROJECTION,
            ordering=Unordered(),
        ),
    )
    return ActivationStatus.DISABLED if result is None else ActivationStatus(result.status)


async def set_statuses_in_session(
    session: DatabaseSession,
    states: tuple[CapabilityActivationState, ...],
) -> None:
    for state in states:
        await session.upsert(
            CAPABILITY_ACTIVATION_STATE_TABLE,
            UpsertCommand(
                key=_key(state.ref),
                row=_record(state.ref, state.activation_status),
            ),
        )


class CapabilityActivationStoreService:
    def __init__(
        self,
        database: Database,
        activation_states: Table[
            CapabilityActivationStateRecord, CapabilityActivationStateKey
        ],
    ) -> None:
        self._database = database
        self._activation_states = activation_states

    async def get_status(self, ref: CapabilityRef) -> ActivationStatus:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            return await get_status_in_session(session, ref)

    async def set_status(self, ref: CapabilityRef, status: ActivationStatus) -> None:
        await self.set_statuses((CapabilityActivationState(ref=ref, activation_status=status),))

    async def set_statuses(self, states: tuple[CapabilityActivationState, ...]) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            changed = tuple([
                state for state in states
                if await get_status_in_session(session, state.ref) != state.activation_status
            ])
            await set_statuses_in_session(session, states)
            for state in changed:
                ref = state.ref
                await append_event_in_session(session, connector_capability_activation_changed_event(
                    ref.connector_kind, ref.connector_id, ref.capability_kind, ref.capability_key,
                ))

    async def reconcile(
        self,
        connector_kind: ConnectorKind,
        connector_id: str,
        capability_kind: CapabilityKind,
        current_keys: tuple[str, ...],
    ) -> None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            deleted = await session.delete(
                self._activation_states,
                DeleteQuery(
                    AllOf(
                        (
                            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_KIND, connector_kind),
                            Equals(CAPABILITY_ACTIVATION_STATE_CONNECTOR_ID, connector_id),
                            Equals(CAPABILITY_ACTIVATION_STATE_CAPABILITY_KIND, capability_kind),
                            Not(
                                OneOf(
                                    CAPABILITY_ACTIVATION_STATE_CAPABILITY_KEY,
                                    current_keys,
                                )
                            ),
                        )
                    )
                ),
            )
            if deleted:
                await append_event_in_session(session, connector_discovery_changed_event(connector_kind, connector_id))


def _key(ref: CapabilityRef) -> CapabilityActivationStateKey:
    return CapabilityActivationStateKey(
        connector_kind=ref.connector_kind,
        connector_id=ref.connector_id,
        capability_kind=ref.capability_kind,
        capability_key=ref.capability_key,
    )


def _record(ref: CapabilityRef, status: ActivationStatus) -> CapabilityActivationStateRecord:
    return CapabilityActivationStateRecord(
        connector_kind=ref.connector_kind,
        connector_id=ref.connector_id,
        capability_kind=ref.capability_kind,
        capability_key=ref.capability_key,
        status=status.value,
        updated_at=_updated_at(),
    )


def _updated_at() -> str:
    return datetime.now(UTC).isoformat()
