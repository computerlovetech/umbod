from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from enum import Enum
from typing import Protocol, TypeVar

from pydantic import BaseModel

from umbod.core.persistence.query import (
    DeleteQuery,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    Query,
    Table,
    UpsertCommand,
)

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class TransactionMode(str, Enum):
    READ_WRITE = "read_write"
    SERIALIZED_WRITE = "serialized_write"


class DatabaseSession(Protocol):
    async def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ResultT | None: ...

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> Sequence[ResultT]: ...

    async def insert(self, table: Table[RowT, KeyT], command: InsertCommand[RowT]) -> bool: ...

    async def insert_generated_integer_key(
        self, table: Table[RowT, KeyT], command: GeneratedIntegerKeyInsertCommand[RowT]
    ) -> int: ...

    async def upsert(
        self, table: Table[RowT, KeyT], command: UpsertCommand[RowT, KeyT]
    ) -> None: ...

    async def delete(self, table: Table[RowT, KeyT], query: DeleteQuery[RowT]) -> int: ...


class DatabaseSchema(Protocol):
    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None: ...


class Database(DatabaseSchema, Protocol):
    def session(self, *, mode: TransactionMode) -> AbstractAsyncContextManager[DatabaseSession]: ...
