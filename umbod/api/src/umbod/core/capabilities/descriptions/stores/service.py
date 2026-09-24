from pydantic import BaseModel, ConfigDict

from umbod.core.capabilities.descriptions.overrides import (
    CapabilityDescriptionOverrideCorruptionError,
    CapabilityDescriptionOverrideState,
    ClearCapabilityDescriptionOverride,
    ConnectorCapabilityDescriptionKey,
    ConnectorKindMismatchError,
    OverriddenCapabilityDescription,
    OverrideRevisionConflictError,
    SetCapabilityDescriptionOverride,
    SystemCapabilityDescription,
)
from umbod.core.capabilities.descriptions.stores.schema import (
    CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID,
    CapabilityDescriptionOverrideKey,
    CapabilityDescriptionOverrideRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    InsertCommand,
    OneOf,
    Query,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


class _OverrideMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: ConnectorCapabilityDescriptionKey
    state: str
    description: str
    expected_revision: int

    def record(self, revision: int) -> CapabilityDescriptionOverrideRecord:
        return CapabilityDescriptionOverrideRecord(
            connector_id=self.key.connector_id,
            connector_kind=self.key.kind,
            state=self.state,
            description=self.description,
            revision=revision,
        )


class ConnectorCapabilityDescriptionOverrideStoreService:
    def __init__(
        self,
        database: Database,
        table: Table[CapabilityDescriptionOverrideRecord, CapabilityDescriptionOverrideKey],
    ) -> None:
        self._database = database
        self._table = table

    async def get(
        self, key: ConnectorCapabilityDescriptionKey
    ) -> CapabilityDescriptionOverrideState:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(
                self._table,
                Query(
                    filter=Equals(CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID, key.connector_id),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
        if row is None:
            return SystemCapabilityDescription(key=key, revision=0)
        return self._decode_row(key, row)

    async def get_many(
        self, keys: tuple[ConnectorCapabilityDescriptionKey, ...]
    ) -> tuple[CapabilityDescriptionOverrideState, ...]:
        if not keys:
            return ()
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = await session.find_many(
                self._table,
                Query(
                    filter=OneOf(
                        CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID,
                        tuple(key.connector_id for key in keys),
                    ),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
        by_id = {row.connector_id: row for row in rows}
        return tuple(
            self._decode_row(key, by_id[key.connector_id])
            if key.connector_id in by_id
            else SystemCapabilityDescription(key=key, revision=0)
            for key in keys
        )

    async def set(
        self, command: SetCapabilityDescriptionOverride
    ) -> OverriddenCapabilityDescription:
        revision = await self._compare_and_swap(
            command.key, "overridden", command.description, command.expected_revision
        )
        return OverriddenCapabilityDescription(
            key=command.key, description=command.description, revision=revision
        )

    async def clear(
        self, command: ClearCapabilityDescriptionOverride
    ) -> SystemCapabilityDescription:
        revision = await self._compare_and_swap(
            command.key, "system", "", command.expected_revision
        )
        return SystemCapabilityDescription(key=command.key, revision=revision)

    async def delete(self, key: ConnectorCapabilityDescriptionKey) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await session.find_one(
                self._table,
                Query(
                    filter=Equals(CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID, key.connector_id),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
            if row is not None:
                self._ensure_kind(key, row)
                await session.delete(
                    self._table,
                    DeleteQuery(
                        Equals(CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID, key.connector_id)
                    ),
                )

    async def _compare_and_swap(
        self,
        key: ConnectorCapabilityDescriptionKey,
        state: str,
        description: str,
        expected_revision: int,
    ) -> int:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            return await self.compare_and_swap_in_session(
                session, key, state, description, expected_revision
            )

    async def get_in_session(
        self,
        session: DatabaseSession,
        key: ConnectorCapabilityDescriptionKey,
    ) -> CapabilityDescriptionOverrideState:
        row = await session.find_one(
            self._table,
            Query(
                filter=Equals(CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID, key.connector_id),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        if row is None:
            return SystemCapabilityDescription(key=key, revision=0)
        return self._decode_row(key, row)

    async def compare_and_swap_in_session(
        self,
        session: DatabaseSession,
        key: ConnectorCapabilityDescriptionKey,
        state: str,
        description: str,
        expected_revision: int,
    ) -> int:
        mutation = _OverrideMutation(
            key=key,
            state=state,
            description=description,
            expected_revision=expected_revision,
        )
        row = await session.find_one(
            self._table,
            Query(
                filter=Equals(CAPABILITY_DESCRIPTION_OVERRIDE_CONNECTOR_ID, key.connector_id),
                projection=AllFields(),
                ordering=Unordered(),
            ),
        )
        if row is None:
            return await self._insert_initial(session, mutation)
        return await self._replace(session, row, mutation)

    async def _insert_initial(
        self,
        session: DatabaseSession,
        mutation: _OverrideMutation,
    ) -> int:
        _ensure_revision(0, mutation.expected_revision)
        record = mutation.record(1)
        if not await session.insert(self._table, InsertCommand(row=record)):
            raise OverrideRevisionConflictError("override changed concurrently")
        return record.revision

    async def _replace(
        self,
        session: DatabaseSession,
        current: CapabilityDescriptionOverrideRecord,
        mutation: _OverrideMutation,
    ) -> int:
        self._ensure_kind(mutation.key, current)
        _ensure_revision(current.revision, mutation.expected_revision)
        record = mutation.record(current.revision + 1)
        await session.upsert(
            self._table,
            UpsertCommand(
                key=CapabilityDescriptionOverrideKey(connector_id=mutation.key.connector_id),
                row=record,
            ),
        )
        return record.revision

    def _decode_row(
        self,
        key: ConnectorCapabilityDescriptionKey,
        row: CapabilityDescriptionOverrideRecord,
    ) -> CapabilityDescriptionOverrideState:
        self._ensure_kind(key, row)
        if row.revision < 1:
            raise CapabilityDescriptionOverrideCorruptionError(
                f"invalid override row for {key.connector_id}"
            )
        if row.state == "system" and not row.description:
            return SystemCapabilityDescription(key=key, revision=row.revision)
        if row.state == "overridden" and row.description:
            try:
                return OverriddenCapabilityDescription(
                    key=key, description=row.description, revision=row.revision
                )
            except ValueError as error:
                raise CapabilityDescriptionOverrideCorruptionError(
                    f"invalid override row for {key.connector_id}"
                ) from error
        raise CapabilityDescriptionOverrideCorruptionError(
            f"invalid override row for {key.connector_id}"
        )

    @staticmethod
    def _ensure_kind(
        key: ConnectorCapabilityDescriptionKey, row: CapabilityDescriptionOverrideRecord
    ) -> None:
        if row.connector_kind != key.kind:
            raise ConnectorKindMismatchError(
                f"connector {key.connector_id} is stored as {row.connector_kind}, not {key.kind}"
            )


def _ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise OverrideRevisionConflictError(f"expected revision {expected}, found {actual}")
