from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field as PydanticField

from umbod.core.invocation.policy import (
    ConnectorInvocationPolicyKey,
    ConnectorInvocationPolicyConflict,
    ConnectorInvocationPolicyRecord,
    ConnectorInvocationPolicyRevisionConflict,
    ConnectorInvocationPolicyStore,
    ConnectorInvocationPolicyUpdate,
    ConnectorKind,
    InvocationPolicyMode,
)
from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Field,
    IntegerCodec,
    KeyCodec,
    Query,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


class ConnectorInvocationPolicyRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: str
    connector_id: str
    operation_name: str
    mode: str
    revision: Annotated[int, PydanticField(ge=0)]


class ConnectorInvocationPolicyRowKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_kind: str
    connector_id: str
    operation_name: str


_IDENTITY = TableIdentity("connector_invocation_policies")
_KIND = Field[ConnectorInvocationPolicyRow, str](_IDENTITY, "connector_kind", TextCodec())
_CONNECTOR_ID = Field[ConnectorInvocationPolicyRow, str](_IDENTITY, "connector_id", TextCodec())
_OPERATION_NAME = Field[ConnectorInvocationPolicyRow, str](_IDENTITY, "operation_name", TextCodec())
_MODE = Field[ConnectorInvocationPolicyRow, str](_IDENTITY, "mode", TextCodec())
_REVISION = Field[ConnectorInvocationPolicyRow, int](_IDENTITY, "revision", IntegerCodec())
_FIELDS = cast(
    tuple[Field[ConnectorInvocationPolicyRow, object], ...],
    (_KIND, _CONNECTOR_ID, _OPERATION_NAME, _MODE, _REVISION),
)
CONNECTOR_INVOCATION_POLICY_TABLE = Table(
    _IDENTITY,
    RowCodec(ConnectorInvocationPolicyRow, _FIELDS),
    KeyCodec(
        ConnectorInvocationPolicyRowKey,
        cast(
            tuple[Field[ConnectorInvocationPolicyRow, object], ...],
            (_KIND, _CONNECTOR_ID, _OPERATION_NAME),
        ),
    ),
)
_ALL = AllFields[ConnectorInvocationPolicyRow]()


def connector_invocation_policy_query(
    key: ConnectorInvocationPolicyKey,
) -> Query[ConnectorInvocationPolicyRow, ConnectorInvocationPolicyRow]:
    return Query(
        filter=AllOf(
            (
                Equals(_KIND, key.connector_kind),
                Equals(_CONNECTOR_ID, key.connector_id),
                Equals(_OPERATION_NAME, key.operation_name),
            )
        ),
        projection=_ALL,
        ordering=Unordered(),
    )


def connector_invocation_policy_record(
    row: ConnectorInvocationPolicyRow,
) -> ConnectorInvocationPolicyRecord:
    if row.connector_kind not in ("native", "openapi", "downstream_mcp"):
        raise ValueError("Invalid stored connector kind")
    if row.mode not in ("direct", "ask"):
        raise ValueError("Invalid stored invocation policy mode")
    return ConnectorInvocationPolicyRecord(
        key=ConnectorInvocationPolicyKey(
            connector_kind=row.connector_kind,
            connector_id=row.connector_id,
            operation_name=row.operation_name,
        ),
        mode=row.mode,
        revision=row.revision,
    )


def _policy_conflicts(
    updates: tuple[ConnectorInvocationPolicyUpdate, ...],
    current_rows: list[ConnectorInvocationPolicyRow | None],
) -> tuple[ConnectorInvocationPolicyConflict, ...]:
    return tuple(
        ConnectorInvocationPolicyConflict(
            key=update.key,
            expected_revision=update.expected_revision,
            current_mode="direct" if row is None else cast(InvocationPolicyMode, row.mode),
            current_revision=0 if row is None else row.revision,
        )
        for update, row in zip(updates, current_rows, strict=True)
        if update.expected_revision != (0 if row is None else row.revision)
    )


async def _apply_persisted_policy_update(
    session: DatabaseSession,
    update: ConnectorInvocationPolicyUpdate,
    current: ConnectorInvocationPolicyRow,
) -> ConnectorInvocationPolicyRecord:
    if current.mode == update.mode:
        return connector_invocation_policy_record(current)
    return await _persist_policy_update(session, update)


async def _apply_missing_policy_update(
    session: DatabaseSession,
    update: ConnectorInvocationPolicyUpdate,
) -> ConnectorInvocationPolicyRecord:
    if update.mode == "direct":
        return ConnectorInvocationPolicyRecord(key=update.key, mode="direct", revision=0)
    return await _persist_policy_update(session, update)


async def _persist_policy_update(
    session: DatabaseSession,
    update: ConnectorInvocationPolicyUpdate,
) -> ConnectorInvocationPolicyRecord:
    row = ConnectorInvocationPolicyRow(
        connector_kind=update.key.connector_kind,
        connector_id=update.key.connector_id,
        operation_name=update.key.operation_name,
        mode=update.mode,
        revision=update.expected_revision + 1,
    )
    await session.upsert(
        CONNECTOR_INVOCATION_POLICY_TABLE,
        UpsertCommand(
            key=ConnectorInvocationPolicyRowKey(
                connector_kind=update.key.connector_kind,
                connector_id=update.key.connector_id,
                operation_name=update.key.operation_name,
            ),
            row=row,
        ),
    )
    return connector_invocation_policy_record(row)


async def compare_and_set_invocation_policies(
    session: DatabaseSession,
    updates: tuple[ConnectorInvocationPolicyUpdate, ...],
) -> tuple[ConnectorInvocationPolicyRecord, ...]:
    current_rows = [
        await session.find_one(
            CONNECTOR_INVOCATION_POLICY_TABLE, connector_invocation_policy_query(update.key)
        )
        for update in updates
    ]
    conflicts = _policy_conflicts(updates, current_rows)
    if conflicts:
        raise ConnectorInvocationPolicyRevisionConflict(conflicts)
    records: list[ConnectorInvocationPolicyRecord] = []
    for update, current in zip(updates, current_rows, strict=True):
        if current is None:
            records.append(await _apply_missing_policy_update(session, update))
        else:
            records.append(await _apply_persisted_policy_update(session, update, current))
    return tuple(records)


async def delete_connector_invocation_policies(
    session: DatabaseSession, connector_kind: ConnectorKind, connector_id: str
) -> None:
    await session.delete(
        CONNECTOR_INVOCATION_POLICY_TABLE,
        DeleteQuery(AllOf((Equals(_KIND, connector_kind), Equals(_CONNECTOR_ID, connector_id)))),
    )


class DatabaseConnectorInvocationPolicyStore(ConnectorInvocationPolicyStore):
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(
        self, key: ConnectorInvocationPolicyKey
    ) -> ConnectorInvocationPolicyRecord | None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(
                CONNECTOR_INVOCATION_POLICY_TABLE, connector_invocation_policy_query(key)
            )
        return None if row is None else connector_invocation_policy_record(row)

    async def list(
        self, keys: tuple[ConnectorInvocationPolicyKey, ...]
    ) -> tuple[ConnectorInvocationPolicyRecord | None, ...]:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = [
                await session.find_one(
                    CONNECTOR_INVOCATION_POLICY_TABLE, connector_invocation_policy_query(key)
                )
                for key in keys
            ]
        return tuple(
            None if row is None else connector_invocation_policy_record(row) for row in rows
        )

    async def delete_connector(self, connector_kind: ConnectorKind, connector_id: str) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await delete_connector_invocation_policies(session, connector_kind, connector_id)

    async def compare_and_set_batch(
        self, updates: tuple[ConnectorInvocationPolicyUpdate, ...]
    ) -> tuple[ConnectorInvocationPolicyRecord, ...]:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            return await compare_and_set_invocation_policies(session, updates)


__all__ = [
    "CONNECTOR_INVOCATION_POLICY_TABLE",
    "DatabaseConnectorInvocationPolicyStore",
    "compare_and_set_invocation_policies",
    "connector_invocation_policy_query",
    "connector_invocation_policy_record",
    "delete_connector_invocation_policies",
]
