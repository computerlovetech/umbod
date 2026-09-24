import asyncio
from collections.abc import AsyncIterator, Mapping, MutableMapping, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import cast

from pydantic import BaseModel

from umbod.core.persistence.ports import DatabaseSession, TransactionMode
from umbod.core.persistence.query import (
    AllOf,
    AnyOf,
    DeleteQuery,
    Equals,
    GeneratedIntegerKeyInsertCommand,
    GreaterThan,
    InsertCommand,
    KeyT,
    NoFilter,
    Not,
    OneOf,
    OrderBy,
    Predicate,
    Query,
    ResultT,
    RowT,
    Table,
    UpsertCommand,
    _decode_result,
    _encode_model,
    validate_query,
)

StoredRow = dict[str, object]
StoredTable = MutableMapping[tuple[object, ...], StoredRow]


class _InMemoryDatabaseSession:
    def __init__(
        self,
        tables: MutableMapping[object, StoredTable],
        generated_integer_keys: MutableMapping[tuple[object, str], int],
    ) -> None:
        self._tables = tables
        self._generated_integer_keys = generated_integer_keys

    async def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ResultT | None:
        rows = await self.find_many(table, query)
        return rows[0] if rows else None

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> Sequence[ResultT]:
        validate_query(table, query)
        rows = [
            row
            for row in self._tables.get(table.identity, {}).values()
            if _matches_predicate(row, query.filter)
        ]
        if isinstance(query.ordering, OrderBy):
            rows.sort(key=lambda row: tuple(row[field.name] for field in query.ordering.fields))
        if query.limit is not None:
            rows = rows[: query.limit]
        return tuple(
            cast(ResultT, _decode_result(table, deepcopy(row), query.projection)) for row in rows
        )

    async def insert(self, table: Table[RowT, KeyT], command: InsertCommand[RowT]) -> bool:
        encoded = _encode_model(table, command.row, table.row_codec.fields)
        key = _encoded_key(table, encoded)
        rows = self._tables.setdefault(table.identity, {})
        if key in rows:
            return False
        rows[key] = deepcopy(encoded)
        return True

    async def insert_generated_integer_key(
        self, table: Table[RowT, KeyT], command: GeneratedIntegerKeyInsertCommand[RowT]
    ) -> int:
        if command.generated_field not in table.key_codec.fields:
            raise ValueError("Generated field must belong to the table key")
        encoded = _encode_model(table, command.row, table.row_codec.fields)
        rows = self._tables.setdefault(table.identity, {})
        counter_key = (table.identity, command.generated_field.name)
        highest_stored_value = max(
            (int(row[command.generated_field.name]) for row in rows.values()), default=0
        )
        generated_value = (
            max(self._generated_integer_keys.get(counter_key, 0), highest_stored_value) + 1
        )
        self._generated_integer_keys[counter_key] = generated_value
        encoded[command.generated_field.name] = generated_value
        rows[_encoded_key(table, encoded)] = deepcopy(encoded)
        return generated_value

    async def upsert(self, table: Table[RowT, KeyT], command: UpsertCommand[RowT, KeyT]) -> None:
        encoded = _encode_model(table, command.row, table.row_codec.fields)
        encoded_key = _encode_model(table, command.key, table.key_codec.fields)
        row_key = _encoded_key(table, encoded)
        key = tuple(encoded_key[field.name] for field in table.key_codec.fields)
        if row_key != key:
            raise ValueError(f"Upsert key does not match row key for {table.name}")
        self._tables.setdefault(table.identity, {})[key] = deepcopy(encoded)

    async def delete(self, table: Table[RowT, KeyT], query: DeleteQuery[RowT]) -> int:
        validate_query(table, query)
        rows = self._tables.get(table.identity, {})
        keys = [key for key, row in rows.items() if _matches_predicate(row, query.filter)]
        for key in keys:
            del rows[key]
        return len(keys)


class InMemoryDatabase:
    def __init__(self) -> None:
        self._tables: dict[object, StoredTable] = {}
        self._generated_integer_keys: dict[tuple[object, str], int] = {}
        self._transaction_lock = asyncio.Lock()

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        async with self._transaction_lock:
            for table in tables:
                self._tables.setdefault(table.identity, {})

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        _ = mode
        async with self._transaction_lock:
            transaction_tables = deepcopy(self._tables)
            transaction_generated_integer_keys = deepcopy(self._generated_integer_keys)
            yield _InMemoryDatabaseSession(transaction_tables, transaction_generated_integer_keys)
            self._tables = transaction_tables
            self._generated_integer_keys = transaction_generated_integer_keys


def _encoded_key(table: Table[RowT, KeyT], row: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(row[field.name] for field in table.key_codec.fields)


def _matches_predicate(row: Mapping[str, object], predicate: Predicate[RowT]) -> bool:
    if isinstance(predicate, NoFilter):
        return True
    if isinstance(predicate, Equals):
        return row[predicate.field.name] == predicate.field.codec.encode(predicate.value)
    if isinstance(predicate, GreaterThan):
        return row[predicate.field.name] > predicate.field.codec.encode(predicate.value)
    if isinstance(predicate, OneOf):
        values = tuple(predicate.field.codec.encode(value) for value in predicate.values)
        return row[predicate.field.name] in values
    if isinstance(predicate, Not):
        return not _matches_predicate(row, predicate.predicate)
    if isinstance(predicate, AllOf):
        return all(_matches_predicate(row, item) for item in predicate.predicates)
    if isinstance(predicate, AnyOf):
        return any(_matches_predicate(row, item) for item in predicate.predicates)
    raise TypeError(f"Unsupported predicate: {type(predicate).__name__}")
