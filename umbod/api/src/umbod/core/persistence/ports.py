from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from enum import Enum
from typing import Protocol, TypeVar

from umbod.proxies import PydanticModel
from umbod.core.persistence.query import (
    DeleteQuery,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    Query,
    Table,
    UpsertCommand,
)

RowT = TypeVar("RowT", bound=PydanticModel)
KeyT = TypeVar("KeyT", bound=PydanticModel)
ResultT = TypeVar("ResultT", bound=PydanticModel)


class TransactionMode(str, Enum):
    READ_WRITE = "read_write"
    SERIALIZED_WRITE = "serialized_write"
    TRY_SERIALIZED_WRITE = "try_serialized_write"


class PersistenceBusyError(RuntimeError):
    pass


class ReadSession(Protocol):
    async def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ResultT | None: ...

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> Sequence[ResultT]: ...


class DatabaseSession(ReadSession, Protocol):
    async def insert(self, table: Table[RowT, KeyT], command: InsertCommand[RowT]) -> bool: ...

    async def insert_generated_integer_key(
        self, table: Table[RowT, KeyT], command: GeneratedIntegerKeyInsertCommand[RowT]
    ) -> int: ...

    async def upsert(
        self, table: Table[RowT, KeyT], command: UpsertCommand[RowT, KeyT]
    ) -> None: ...

    async def delete(self, table: Table[RowT, KeyT], query: DeleteQuery[RowT]) -> int: ...


class DatabaseSchema(Protocol):
    async def ensure_schema(self, tables: Sequence[Table[PydanticModel, PydanticModel]]) -> None: ...


class Database(DatabaseSchema, Protocol):
    def read_session(self) -> AbstractAsyncContextManager[ReadSession]: ...

    def session(self, *, mode: TransactionMode) -> AbstractAsyncContextManager[DatabaseSession]: ...
