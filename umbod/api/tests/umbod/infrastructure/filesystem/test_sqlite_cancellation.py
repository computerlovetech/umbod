import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio
from pydantic import BaseModel

from umbod.core.filesystem import NamespaceDriver, Node, NodeKind, NodeMetadata
from umbod.core.persistence import (
    Database,
    DatabaseSession,
    PersistenceRuntime,
    Table,
    TransactionMode,
)
from umbod.infrastructure import create_namespace_driver
from tests.persistence_runtime import prepared_sqlite_runtime


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[PersistenceRuntime]:
    instance = await prepared_sqlite_runtime(tmp_path / "cancellation.db")
    try:
        yield instance
    finally:
        await instance.shutdown()


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type="text/plain", attributes={})


@pytest.mark.asyncio
async def test_task_cancelled_while_waiting_for_sqlite_writer_releases_connection(
    runtime: PersistenceRuntime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace: NamespaceDriver = create_namespace_driver(database=runtime.database)
    root = await namespace.get_root()
    entered = asyncio.Event()
    execute = aiosqlite.Connection.execute

    async def observed_execute(
        connection: aiosqlite.Connection, statement: str, *parameters: object,
    ) -> aiosqlite.Cursor:
        if statement == "BEGIN IMMEDIATE" and asyncio.current_task() is task:
            entered.set()
        return await execute(connection, statement, *parameters)

    async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE):
        monkeypatch.setattr(aiosqlite.Connection, "execute", observed_execute)
        task: asyncio.Task[Node] = asyncio.create_task(namespace.create_node(
            root.id, "cancelled", NodeKind.FILE, metadata(),
        ))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
        finally:
            task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert tuple(await namespace.list_children(root.id)) == ()
    retained = await asyncio.wait_for(namespace.create_node(
        root.id, "retained", NodeKind.FILE, metadata(),
    ), timeout=5)
    assert tuple(await namespace.list_children(root.id)) == (retained,)


class PausingCommitDatabase:
    def __init__(
        self, database: Database, mutation_applied: asyncio.Event, commit_allowed: asyncio.Event,
    ) -> None:
        self._database = database
        self._mutation_applied = mutation_applied
        self._commit_allowed = commit_allowed

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        await self._database.ensure_schema(tables)

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with self._database.session(mode=mode) as session:
            yield session
            self._mutation_applied.set()
            await self._commit_allowed.wait()


@pytest.mark.asyncio
async def test_task_cancelled_after_sqlite_mutation_rolls_back_before_returning(
    runtime: PersistenceRuntime,
) -> None:
    namespace: NamespaceDriver = create_namespace_driver(database=runtime.database)
    root = await namespace.get_root()
    mutation_applied = asyncio.Event()
    commit_allowed = asyncio.Event()
    paused: Database = PausingCommitDatabase(runtime.database, mutation_applied, commit_allowed)
    operation: NamespaceDriver = create_namespace_driver(database=paused)
    task = asyncio.create_task(operation.create_node(
        root.id, "cancelled", NodeKind.FILE, metadata(),
    ))
    try:
        await asyncio.wait_for(mutation_applied.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert tuple(await namespace.list_children(root.id)) == ()
    retained = await asyncio.wait_for(namespace.create_node(
        root.id, "retained", NodeKind.FILE, metadata(),
    ), timeout=5)
    assert tuple(await namespace.list_children(root.id)) == (retained,)
