from typing import cast

import pytest
from pydantic import BaseModel, ConfigDict

from tests.support.persistence_contracts import SampleRow, table
from umbod.core.persistence import (
    AllFields,
    AllOf,
    AnyOf,
    Database,
    DeleteQuery,
    Equals,
    Field,
    Fields,
    InsertCommand,
    KeyCodec,
    NoFilter,
    Not,
    OneOf,
    OrderBy,
    Query,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
    TransactionMode,
    UpsertCommand,
)


class QualifiedKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    namespace: str
    owner_id: str
    record_kind: str
    record_id: str


class QualifiedRow(QualifiedKey):
    payload: str


def qualified_table() -> Table[QualifiedRow, QualifiedKey]:
    identity = TableIdentity("qualified_records")
    fields = cast(tuple[Field[QualifiedRow, object], ...], tuple(
        Field[QualifiedRow, str](identity, name, TextCodec())
        for name in ("namespace", "owner_id", "record_kind", "record_id", "payload")
    ))
    return Table(identity, RowCodec(QualifiedRow, fields), KeyCodec(QualifiedKey, fields[:4]))


def qualified_identity(value: QualifiedRow) -> tuple[str, ...]:
    return value.namespace, value.owner_id, value.record_kind, value.record_id


@pytest.mark.asyncio
async def test_composite_keys_isolate_rows_with_colliding_components(database: Database) -> None:
    contract_table = qualified_table()
    await database.ensure_schema((contract_table,))
    original = QualifiedRow(
        namespace="trusted", owner_id="owner", record_kind="tool", record_id="shared", payload="original",
    )
    neighbours = tuple(original.model_copy(update={field: "other", "payload": field}) for field in QualifiedKey.model_fields)
    target = AllOf(tuple(Equals(field, getattr(original, field.name)) for field in contract_table.key_codec.fields))
    ordering = OrderBy(contract_table.key_codec.fields)
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for value in (original, *neighbours):
            assert await session.insert(contract_table, InsertCommand(row=value))
        assert not await session.insert(
            contract_table, InsertCommand(row=original.model_copy(update={"payload": "duplicate"})),
        )
    async with database.read_session() as session:
        assert await session.find_one(contract_table, Query(target, AllFields(), ordering)) == original

    updated = original.model_copy(update={"payload": "updated"})
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        await session.upsert(
            contract_table,
            UpsertCommand(key=QualifiedKey.model_validate(original.model_dump()), row=updated),
        )
    async with database.read_session() as session:
        assert await session.find_one(contract_table, Query(target, AllFields(), ordering)) == updated
        assert await session.find_many(contract_table, Query(NoFilter(), AllFields(), ordering)) == tuple(
            sorted((*neighbours, updated), key=qualified_identity),
        )

    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.delete(contract_table, DeleteQuery(target)) == 1
    async with database.read_session() as session:
        assert await session.find_many(contract_table, Query(NoFilter(), AllFields(), ordering)) == tuple(
            sorted(neighbours, key=qualified_identity),
        )


@pytest.mark.asyncio
async def test_compound_membership_queries_preserve_scope_across_large_and_partial_batches(
    database: Database,
) -> None:
    contract_table, owner, record, _ = table("batched_membership")
    await database.ensure_schema((contract_table,))
    identifiers = tuple(f"record-{index:03}" for index in range(401))
    matching = tuple(SampleRow(owner_id="owner-a", record_id=value, payload=value) for value in identifiers) + tuple(
        SampleRow(owner_id="owner-c", record_id=value, payload=value)
        for value in (identifiers[199], identifiers[200], identifiers[400])
    )
    distractors = tuple(SampleRow(owner_id="owner-b", record_id=value, payload="excluded") for value in identifiers) + (
        SampleRow(owner_id="owner-a", record_id="outside", payload="excluded"),
    )
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for value in (*matching, *distractors):
            await session.insert(contract_table, InsertCommand(row=value))
    observed: list[SampleRow] = []
    async with database.read_session() as session:
        for offset in range(0, len(identifiers), 200):
            batch = identifiers[offset:offset + 200]
            observed.extend(await session.find_many(
                contract_table,
                Query(
                    AllOf((
                        OneOf(owner, ("owner-a", "owner-c", "owner-a")),
                        OneOf(record, batch + batch[:1]),
                    )),
                    AllFields(), OrderBy((owner, record)),
                ),
            ))
    assert tuple(sorted(observed, key=lambda value: (value.owner_id, value.record_id))) == matching


@pytest.mark.asyncio
async def test_nested_disjunction_preserves_global_filters_branch_scopes_and_projection(
    database: Database,
) -> None:
    contract_table = qualified_table()
    namespace, owner, kind, record = contract_table.key_codec.fields
    payload = contract_table.row_codec.fields[-1]
    matching = (
        QualifiedRow(namespace="trusted", owner_id="owner-a", record_kind="tool", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-common", record_kind="tool", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-b", record_kind="prompt", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-common", record_kind="prompt", record_id="shared", payload="enabled"),
    )
    distractors = (
        QualifiedRow(namespace="trusted", owner_id="owner-b", record_kind="tool", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-a", record_kind="prompt", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-common", record_kind="resource", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="other", owner_id="owner-a", record_kind="tool", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-a", record_kind="tool", record_id="disabled", payload="disabled"),
        QualifiedRow(namespace="trusted", owner_id="unselected", record_kind="tool", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="other", owner_id="owner-b", record_kind="prompt", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-b", record_kind="prompt", record_id="disabled", payload="disabled"),
        QualifiedRow(namespace="other", owner_id="owner-common", record_kind="tool", record_id="shared", payload="enabled"),
        QualifiedRow(namespace="trusted", owner_id="owner-common", record_kind="tool", record_id="disabled", payload="disabled"),
    )
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for value in (*matching, *distractors):
            await session.insert(contract_table, InsertCommand(row=value))
    predicate = AllOf((
        Equals(namespace, "trusted"),
        Equals(payload, "enabled"),
        AnyOf((
            AllOf((Equals(kind, "tool"), OneOf(owner, ("owner-a", "owner-common")))),
            AllOf((Equals(kind, "prompt"), OneOf(owner, ("owner-b", "owner-common")))),
            AllOf((Equals(kind, "tool"), OneOf(owner, ("owner-common",)))),
        )),
    ))
    async with database.read_session() as session:
        projected = await session.find_many(
            contract_table,
            Query(predicate, Fields(QualifiedKey, (namespace, owner, kind, record)), OrderBy(contract_table.key_codec.fields)),
        )
    assert projected == tuple(
        QualifiedKey.model_validate(value.model_dump()) for value in sorted(matching, key=qualified_identity)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retained_keys", "remaining_keys", "deleted_count"),
    (
        ((), (), 2),
        (("keep",), ("keep",), 1),
        (("missing",), (), 2),
        (("keep", "remove"), ("keep", "remove"), 0),
        (("keep", "keep", "missing"), ("keep",), 1),
    ),
)
async def test_scoped_negated_membership_deletes_only_unretained_rows(
    database: Database, retained_keys: tuple[str, ...], remaining_keys: tuple[str, ...], deleted_count: int,
) -> None:
    contract_table = qualified_table()
    namespace, owner, kind, record = contract_table.key_codec.fields
    target_rows = tuple(
        QualifiedRow(namespace="trusted", owner_id="owner", record_kind="tool", record_id=key, payload=key)
        for key in ("keep", "remove")
    )
    neighbours = tuple(
        value.model_copy(update={field: "other"})
        for field in ("namespace", "owner_id", "record_kind") for value in target_rows
    )
    await database.ensure_schema((contract_table,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        for value in (*target_rows, *neighbours):
            await session.insert(contract_table, InsertCommand(row=value))
    deletion = DeleteQuery(AllOf((
        Equals(namespace, "trusted"), Equals(owner, "owner"), Equals(kind, "tool"),
        Not(OneOf(record, retained_keys)),
    )))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.delete(contract_table, deletion) == deleted_count
    expected = (*neighbours, *(value for value in target_rows if value.record_id in remaining_keys))
    async with database.read_session() as session:
        assert await session.find_many(
            contract_table, Query(NoFilter(), AllFields(), OrderBy(contract_table.key_codec.fields)),
        ) == tuple(sorted(expected, key=qualified_identity))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.delete(contract_table, deletion) == 0
