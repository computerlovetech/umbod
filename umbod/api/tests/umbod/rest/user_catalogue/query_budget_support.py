from collections import Counter
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Optional, TypeVar

from pydantic import BaseModel

from umbod.core.persistence import (
    Database,
    DatabaseSession,
    DeleteQuery,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    PersistenceReadiness,
    PersistenceRuntime,
    Query,
    ReadSession,
    Table,
    TransactionMode,
    UpsertCommand,
)

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class QueryCounts:
    def __init__(self) -> None:
        self.reads: Counter[str] = Counter()
        self.writes: Counter[str] = Counter()
        self.sessions = 0
        self.schema_calls = 0

    def reset(self) -> None:
        self.reads.clear()
        self.writes.clear()
        self.sessions = 0
        self.schema_calls = 0


class CountingReadSession:
    def __init__(self, session: ReadSession, counts: QueryCounts) -> None:
        self.session = session
        self.counts = counts

    async def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT],
    ) -> Optional[ResultT]:
        self.counts.reads[table.name] += 1
        return await self.session.find_one(table, query)

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT],
    ) -> Sequence[ResultT]:
        self.counts.reads[table.name] += 1
        return await self.session.find_many(table, query)


class CountingSession(CountingReadSession):
    def __init__(self, session: DatabaseSession, counts: QueryCounts) -> None:
        super().__init__(session, counts)
        self.session: DatabaseSession = session

    async def insert(self, table: Table[RowT, KeyT], command: InsertCommand[RowT]) -> bool:
        self.counts.writes[table.name] += 1
        return await self.session.insert(table, command)

    async def insert_generated_integer_key(
        self, table: Table[RowT, KeyT], command: GeneratedIntegerKeyInsertCommand[RowT],
    ) -> int:
        self.counts.writes[table.name] += 1
        return await self.session.insert_generated_integer_key(table, command)

    async def upsert(
        self, table: Table[RowT, KeyT], command: UpsertCommand[RowT, KeyT],
    ) -> None:
        self.counts.writes[table.name] += 1
        await self.session.upsert(table, command)

    async def delete(self, table: Table[RowT, KeyT], query: DeleteQuery[RowT]) -> int:
        self.counts.writes[table.name] += 1
        return await self.session.delete(table, query)


class CountingDatabase:
    def __init__(self, database: Database, counts: QueryCounts) -> None:
        self.database = database
        self.counts = counts

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        self.counts.schema_calls += 1
        await self.database.ensure_schema(tables)

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.counts.sessions += 1
        async with self.database.read_session() as session:
            yield CountingReadSession(session, self.counts)

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        self.counts.sessions += 1
        async with self.database.session(mode=mode) as session:
            yield CountingSession(session, self.counts)


class CountingRuntime:
    def __init__(self, runtime: PersistenceRuntime, counts: QueryCounts) -> None:
        self.runtime = runtime
        self.counted_database = CountingDatabase(runtime.database, counts)

    @property
    def database(self) -> Database:
        return self.counted_database

    @property
    def readiness(self) -> PersistenceReadiness:
        return self.runtime.readiness

    async def shutdown(self) -> None:
        await self.runtime.shutdown()
