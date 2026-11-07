import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import aiosqlite
import anyio
import pytest
import pytest_asyncio

from tests.support.persistence_contracts import row, table
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database


Owner = Literal["read_session", "session", "schema_connection", "ensure_schema"]


@dataclass
class ConnectionTracker:
    connections: list[aiosqlite.Connection] = field(default_factory=list)
    workers: list[threading.Thread] = field(default_factory=list)
    closed: list[aiosqlite.Connection] = field(default_factory=list)
    rolled_back: list[aiosqlite.Connection] = field(default_factory=list)

    async def assert_released(self) -> None:
        assert self.connections
        assert self.closed == self.connections
        for worker in self.workers:
            await asyncio.to_thread(worker.join, 2)
            assert not worker.is_alive()
        assert len(self.workers) == len(self.connections)


@pytest_asyncio.fixture
async def connections(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[ConnectionTracker]:
    tracker = ConnectionTracker()
    connect = aiosqlite.connect
    close = aiosqlite.Connection.close
    rollback = aiosqlite.Connection.rollback
    start = threading.Thread.start

    def tracked_connect(*args: Any, **kwargs: Any) -> aiosqlite.Connection:
        connection = connect(*args, **kwargs)
        tracker.connections.append(connection)
        return connection

    def tracked_start(worker: threading.Thread) -> None:
        if "_connection_worker_thread" in worker.name:
            tracker.workers.append(worker)
        start(worker)

    async def tracked_close(connection: aiosqlite.Connection) -> None:
        await close(connection)
        tracker.closed.append(connection)

    async def tracked_rollback(connection: aiosqlite.Connection) -> None:
        await rollback(connection)
        tracker.rolled_back.append(connection)

    monkeypatch.setattr(aiosqlite, "connect", tracked_connect)
    monkeypatch.setattr(aiosqlite.Connection, "close", tracked_close)
    monkeypatch.setattr(aiosqlite.Connection, "rollback", tracked_rollback)
    monkeypatch.setattr(threading.Thread, "start", tracked_start)
    try:
        yield tracker
    finally:
        for connection in tracker.connections:
            await close(connection)
        for worker in tracker.workers:
            await asyncio.to_thread(worker.join, 2)


async def _run_owner(database: SQLiteDatabase, owner: Owner) -> None:
    if owner == "ensure_schema":
        await database.ensure_schema(())
    elif owner == "read_session":
        async with database.read_session():
            pass
    elif owner == "schema_connection":
        async with database.schema_connection():
            pass
    else:
        async with database.session(mode=TransactionMode.READ_WRITE):
            pass


async def _checkpoints() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


async def _finish_task(task: asyncio.Task[None]) -> None:
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", (RuntimeError, asyncio.CancelledError))
@pytest.mark.parametrize(
    ("owner", "statement"),
    (
        ("read_session", "PRAGMA foreign_keys=ON"),
        ("read_session", "PRAGMA busy_timeout=5000"),
        ("session", "PRAGMA foreign_keys=ON"),
        ("schema_connection", "PRAGMA busy_timeout=5000"),
        ("ensure_schema", "PRAGMA foreign_keys=ON"),
        ("read_session", "PRAGMA query_only=ON"),
        ("ensure_schema", "PRAGMA journal_mode=WAL"),
    ),
)
async def test_pragma_failure_closes_connection_and_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    connections: ConnectionTracker,
    owner: Owner,
    statement: str,
    failure: type[BaseException],
) -> None:
    execute = aiosqlite.Connection.execute

    async def failing_execute(
        connection: aiosqlite.Connection, sql: str, *args: Any, **kwargs: Any
    ) -> aiosqlite.Cursor:
        if sql == statement:
            raise failure("configuration interrupted")
        return await execute(connection, sql, *args, **kwargs)

    monkeypatch.setattr(aiosqlite.Connection, "execute", failing_execute)
    database = create_unpooled_sqlite_database(str(tmp_path / "configuration.sqlite"), create_parent_dirs=False)
    with pytest.raises(failure, match="configuration interrupted"):
        await _run_owner(database, owner)
    await connections.assert_released()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ("read_session", "session", "schema_connection", "ensure_schema"))
async def test_cancellation_waits_for_pending_driver_open_before_returning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    connections: ConnectionTracker,
    owner: Owner,
) -> None:
    loop = asyncio.get_running_loop()
    opening = asyncio.Event()
    release = threading.Event()
    connect = sqlite3.connect

    def paused_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        loop.call_soon_threadsafe(opening.set)
        if not release.wait(5):
            raise TimeoutError("driver connector was not released")
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", paused_connect)
    database = create_unpooled_sqlite_database(str(tmp_path / "opening.sqlite"), create_parent_dirs=False)
    task = asyncio.create_task(_run_owner(database, owner))
    try:
        await asyncio.wait_for(opening.wait(), 2)
        task.cancel()
        await _checkpoints()
        assert not task.done()
        assert any(worker.is_alive() for worker in connections.workers)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), 2)
        await connections.assert_released()
    finally:
        release.set()
        await _finish_task(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("rollback", "close"))
@pytest.mark.parametrize("owner", ("read_session", "session", "schema_connection", "ensure_schema"))
async def test_repeated_task_cancellation_does_not_interrupt_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    connections: ConnectionTracker,
    owner: Owner,
    phase: Literal["rollback", "close"],
) -> None:
    entered = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()
    execute = aiosqlite.Connection.execute
    cleanup = getattr(aiosqlite.Connection, phase)

    async def paused_execute(
        connection: aiosqlite.Connection, sql: str, *args: Any, **kwargs: Any
    ) -> aiosqlite.Cursor:
        cursor = await execute(connection, sql, *args, **kwargs)
        if sql.startswith("BEGIN") or (
            owner == "ensure_schema" and sql == "PRAGMA journal_mode=WAL"
        ):
            entered.set()
            await asyncio.Event().wait()
        return cursor

    async def paused_cleanup(connection: aiosqlite.Connection) -> None:
        cleaning.set()
        await release.wait()
        await cleanup(connection)

    monkeypatch.setattr(aiosqlite.Connection, "execute", paused_execute)
    monkeypatch.setattr(aiosqlite.Connection, phase, paused_cleanup)
    database = create_unpooled_sqlite_database(str(tmp_path / "repeated.sqlite"), create_parent_dirs=False)
    task = asyncio.create_task(_run_owner(database, owner))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 2)
        for _ in range(3):
            task.cancel()
            await _checkpoints()
            assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), 2)
        assert connections.rolled_back == connections.connections
        await connections.assert_released()
    finally:
        release.set()
        await _finish_task(task)


@pytest.mark.asyncio
async def test_anyio_cancelled_scope_rolls_back_write_and_closes_connection(
    tmp_path: Path, connections: ConnectionTracker
) -> None:
    database = create_unpooled_sqlite_database(str(tmp_path / "scope.sqlite"), create_parent_dirs=False)
    records, _, _, _ = table("scope_records")
    await database.ensure_schema((records,))
    with anyio.CancelScope() as scope:
        async with database.session(mode=TransactionMode.READ_WRITE) as session:
            await session.insert(records, InsertCommand(row=row("cancelled")))
            scope.cancel()
            await anyio.lowlevel.checkpoint()
    assert connections.rolled_back == [connections.connections[1]]
    await connections.assert_released()
    async with database.read_session() as session:
        assert await session.find_many(records, Query(NoFilter(), AllFields(), Unordered())) == ()
    await connections.assert_released()


async def _assert_failed_connector_drains_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    connections: ConnectionTracker,
    cancel_opening: bool,
) -> None:
    loop = asyncio.get_running_loop()
    opening = asyncio.Event()
    stopping = asyncio.Event()
    release_connector = threading.Event()
    release_stop = asyncio.Event()
    stop = aiosqlite.Connection.stop
    stop_tasks: list[asyncio.Task[None]] = []

    def failing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        loop.call_soon_threadsafe(opening.set)
        if not release_connector.wait(5):
            raise TimeoutError("failing connector was not released")
        raise sqlite3.OperationalError("driver opening failed")

    def delayed_stop(connection: aiosqlite.Connection) -> asyncio.Future[None]:
        stopped = stop(connection)
        assert stopped is not None

        async def finish_stop() -> None:
            await stopped
            await release_stop.wait()

        pending = asyncio.create_task(finish_stop())
        stop_tasks.append(pending)
        stopping.set()
        return pending

    monkeypatch.setattr(sqlite3, "connect", failing_connect)
    monkeypatch.setattr(aiosqlite.Connection, "stop", delayed_stop)
    database = create_unpooled_sqlite_database(str(tmp_path / "failed-opening.sqlite"), create_parent_dirs=False)
    task = asyncio.create_task(_run_owner(database, "read_session"))
    try:
        await asyncio.wait_for(opening.wait(), 2)
        if cancel_opening:
            task.cancel()
            await _checkpoints()
            assert not task.done()
        release_connector.set()
        await asyncio.wait_for(stopping.wait(), 2)
        await _checkpoints()
        assert not task.done()
        release_stop.set()
        if cancel_opening:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), 2)
        else:
            with pytest.raises(sqlite3.OperationalError, match="driver opening failed"):
                await asyncio.wait_for(asyncio.shield(task), 2)
        await connections.assert_released()
    finally:
        release_connector.set()
        release_stop.set()
        await _finish_task(task)
        await asyncio.gather(*stop_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_driver_open_drains_worker_stop_before_returning_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, connections: ConnectionTracker
) -> None:
    await _assert_failed_connector_drains_stop(tmp_path, monkeypatch, connections, False)


@pytest.mark.asyncio
async def test_cancelled_driver_open_drains_eventual_failure_and_preserves_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, connections: ConnectionTracker
) -> None:
    await _assert_failed_connector_drains_stop(tmp_path, monkeypatch, connections, True)


@pytest.mark.asyncio
async def test_successful_write_remains_committed_after_connection_cleanup(
    tmp_path: Path, connections: ConnectionTracker
) -> None:
    database = create_unpooled_sqlite_database(str(tmp_path / "commit.sqlite"), create_parent_dirs=False)
    records, _, _, _ = table("committed_records")
    expected = row("committed", "preserved")
    await database.ensure_schema((records,))
    async with database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.insert(records, InsertCommand(row=expected))
    async with database.read_session() as session:
        assert await session.find_many(records, Query(NoFilter(), AllFields(), Unordered())) == (expected,)
    await connections.assert_released()
