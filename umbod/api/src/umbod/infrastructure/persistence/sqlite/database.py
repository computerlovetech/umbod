import aiosqlite

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from umbod.core.persistence.ports import DatabaseSession, TransactionMode
from umbod.core.persistence.query import (
    AllFields,
    DeleteQuery,
    GeneratedIntegerKeyInsertCommand,
    InsertCommand,
    KeyT,
    PersistenceDecodingError,
    Query,
    ResultT,
    RowT,
    Table,
    UpsertCommand,
    _decode_result,
    _encode_model,
)
from umbod.infrastructure.persistence.sqlite.compiler import SQLiteCompiler
from umbod.infrastructure.persistence.sqlite.value_mapping import SQLiteValueMapper


class _SQLiteDatabaseSession:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._mapper = SQLiteValueMapper()
        self._compiler = SQLiteCompiler(self._mapper)

    async def find_one(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> ResultT | None:
        compiled = self._compiler.select(table, query, limit_one=True)
        cursor = await self._connection.execute(compiled.statement, compiled.parameters)
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return cast(ResultT, self._decode_row(table, query, dict(row)))

    async def find_many(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]
    ) -> Sequence[ResultT]:
        compiled = self._compiler.select(table, query, limit_one=False)
        cursor = await self._connection.execute(compiled.statement, compiled.parameters)
        rows = await cursor.fetchall()
        await cursor.close()
        return tuple(cast(ResultT, self._decode_row(table, query, dict(row))) for row in rows)

    def _decode_row(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT], row: dict[str, object]
    ) -> RowT | ResultT:
        fields = (
            table.row_codec.fields
            if isinstance(query.projection, AllFields)
            else query.projection.fields
        )
        canonical: dict[str, object] = {}
        for field in fields:
            try:
                canonical[field.name] = self._mapper.unbind(
                    field.codec.column_type, row[field.name]
                )
            except (KeyError, TypeError, ValueError) as error:
                raise PersistenceDecodingError(table.name, field.name, error) from error
        return _decode_result(table, canonical, query.projection)

    async def insert(self, table: Table[RowT, KeyT], command: InsertCommand[RowT]) -> bool:
        compiled = self._compiler.insert(table, command)
        try:
            cursor = await self._connection.execute(compiled.statement, compiled.parameters)
            await cursor.close()
        except aiosqlite.IntegrityError:
            keys = _encode_model(table, command.row, table.key_codec.fields)
            lookup = self._compiler.key_exists(table, keys)
            cursor = await self._connection.execute(lookup.statement, lookup.parameters)
            exists = await cursor.fetchone()
            await cursor.close()
            if exists is not None:
                return False
            raise
        return True

    async def insert_generated_integer_key(
        self, table: Table[RowT, KeyT], command: GeneratedIntegerKeyInsertCommand[RowT]
    ) -> int:
        compiled = self._compiler.insert_generated_integer_key(table, command)
        cursor = await self._connection.execute(compiled.statement, compiled.parameters)
        generated_value = cursor.lastrowid
        await cursor.close()
        if generated_value is None:
            raise RuntimeError("SQLite did not return a generated integer key")
        return int(generated_value)

    async def upsert(self, table: Table[RowT, KeyT], command: UpsertCommand[RowT, KeyT]) -> None:
        compiled = self._compiler.upsert(table, command)
        cursor = await self._connection.execute(compiled.statement, compiled.parameters)
        await cursor.close()

    async def delete(self, table: Table[RowT, KeyT], query: DeleteQuery[RowT]) -> int:
        compiled = self._compiler.delete(table, query)
        cursor = await self._connection.execute(compiled.statement, compiled.parameters)
        row_count = int(cursor.rowcount)
        await cursor.close()
        return row_count


class SQLiteDatabase:
    def __init__(self, database_path: str, *, create_parent_dirs: bool) -> None:
        self._database_path = database_path
        self._create_parent_dirs = create_parent_dirs

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        if self._create_parent_dirs:
            parent = Path(self._database_path).parent
            if str(parent) != ".":
                parent.mkdir(parents=True, exist_ok=True)
        connection = await self._connect()
        compiler = SQLiteCompiler(SQLiteValueMapper())
        try:
            await connection.execute("PRAGMA journal_mode=WAL")
            for table in tables:
                compiled = compiler.create_table(table)
                await connection.execute(compiled.statement, compiled.parameters)
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    @asynccontextmanager
    async def schema_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await self._connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            yield connection
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        connection = await self._connect()
        try:
            statement = "BEGIN IMMEDIATE" if mode is TransactionMode.SERIALIZED_WRITE else "BEGIN"
            await connection.execute(statement)
            yield _SQLiteDatabaseSession(connection)
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def _connect(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self._database_path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("PRAGMA busy_timeout=5000")
        return connection
