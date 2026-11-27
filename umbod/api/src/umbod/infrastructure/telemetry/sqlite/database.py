import asyncio
import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiosqlite

from umbod.config.defaults import TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS
from umbod.core.activity.ports import HarnessActivityReader
from umbod.core.telemetry.analytics import (
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
)

from umbod.infrastructure.connections import (
    ConnectionPool,
    ConnectionPoolUnavailableError,
    ConnectionProvider,
)
from umbod.infrastructure.connections.lifecycle import complete_cleanup
from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver

from .retention import archive_cutoff_us, expire_raw_archives, utc_now
from .schema import ensure_schema

ARCHIVE_SWEEP_INTERVAL_SECONDS = 3600
ARCHIVE_SWEEP_RETRY_SECONDS = 60


def validate_path(database_path: Path, protected_paths: tuple[Path, ...]) -> Path:
    raw = str(database_path)
    if (
        not raw.strip()
        or raw == "."
        or ":memory:" in raw.lower()
        or raw.strip().lower().startswith("file:")
        or "\x00" in raw
    ):
        raise ValueError("Analytics requires a separate file-backed database")
    path = database_path.resolve()
    analytics_files = related_files(path)
    for protected in protected_paths:
        protected_files = related_files(protected)
        for candidate in analytics_files:
            for other in protected_files:
                if candidate == other or (
                    candidate.exists() and other.exists() and candidate.samefile(other)
                ):
                    raise ValueError("Analytics database must be separate")
    return path


def related_files(path: Path) -> tuple[Path, ...]:
    return tuple(
        {
            Path(str(base) + suffix).resolve()
            for base in (path, path.resolve())
            for suffix in ("", "-wal", "-shm", "-journal")
        }
    )


def prepare_directory(path: Path, protected_paths: tuple[Path, ...]) -> None:
    validate_path(path, protected_paths)
    path.parent.mkdir(parents=True, exist_ok=True)


class SqliteAnalyticsRuntime:
    def __init__(self, database_path: Path, protected_paths: tuple[Path, ...]) -> None:
        self._retention_days = TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS
        self._clock: Callable[[], datetime] = utc_now
        self._sweeper: asyncio.Task[None] | None = None
        try:
            self._path = validate_path(database_path, protected_paths)
            self._protected_paths = tuple(path.absolute() for path in protected_paths)
        except (OSError, RuntimeError):
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        self._connections: ConnectionProvider[aiosqlite.Connection] = ConnectionPool(
            SQLiteConnectionDriver(str(self._path), create_parent_dirs=False), size=2
        )
        self._condition = asyncio.Condition()
        self._readiness_lock = asyncio.Lock()
        self._ready = False
        self._closed = False
        self._active = 0

    @classmethod
    def with_retention(
        cls,
        database_path: Path,
        protected_paths: tuple[Path, ...],
        raw_archive_retention_days: int,
        clock: Callable[[], datetime],
    ) -> "SqliteAnalyticsRuntime":
        if raw_archive_retention_days < 1:
            raise ValueError("Analytics archive retention must be positive")
        runtime = cls(database_path, protected_paths)
        runtime._retention_days = raw_archive_retention_days
        runtime._clock = clock
        return runtime

    def archive_cutoff_us(self) -> int:
        return archive_cutoff_us(self._clock(), self._retention_days)

    def create_reader(self) -> TelemetryAnalyticsReader:
        from .reader import SqliteAnalyticsReader

        return SqliteAnalyticsReader(self)

    def create_harness_activity_reader(self) -> HarnessActivityReader:
        from .activity_reader import SqliteHarnessActivityReader

        return SqliteHarnessActivityReader(self)

    def create_writer(self) -> TelemetryAnalyticsWriter:
        from .writer import SqliteAnalyticsWriter

        return SqliteAnalyticsWriter(self)

    @asynccontextmanager
    async def _operation(self) -> AsyncIterator[None]:
        async with self._condition:
            if self._closed:
                raise TelemetryAnalyticsUnavailable(
                    "Telemetry analytics is unavailable"
                )
            self._active += 1
        try:
            yield
        except (
            sqlite3.Error,
            OSError,
            ValueError,
            TypeError,
            OverflowError,
            ConnectionPoolUnavailableError,
        ):
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        finally:
            await complete_cleanup(self._finish_operation())

    async def _finish_operation(self) -> None:
        async with self._condition:
            self._active -= 1
            self._condition.notify_all()

    async def _prepare(self) -> None:
        async with self._readiness_lock:
            if self._ready:
                return
            preparing = asyncio.create_task(
                asyncio.to_thread(prepare_directory, self._path, self._protected_paths)
            )
            try:
                await asyncio.shield(preparing)
            finally:
                await complete_cleanup(preparing)
            await self._connections.initialize()
            async with self._connections.get_connection() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                await ensure_schema(connection)
                await connection.commit()
                async with connection.execute("PRAGMA journal_mode = WAL") as cursor:
                    journal_mode = (await cursor.fetchone())[0]
                if journal_mode != "wal":
                    raise ValueError("Analytics requires WAL journal mode")
            next_sweep = await self._sweep_archives_once()
            self._ready = True
            if not self._closed:
                self._sweeper = asyncio.create_task(self._sweep_archives(next_sweep))

    async def _sweep_archives_once(self) -> float:
        started_at = asyncio.get_running_loop().time()
        try:
            async with self._operation():
                async with self._connections.get_connection() as connection:
                    await expire_raw_archives(connection, self.archive_cutoff_us())
        except TelemetryAnalyticsUnavailable:
            return started_at + ARCHIVE_SWEEP_RETRY_SECONDS
        return started_at + ARCHIVE_SWEEP_INTERVAL_SECONDS

    async def _sweep_archives(self, next_sweep: float) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(max(0, next_sweep - loop.time()))
            next_sweep = await self._sweep_archives_once()

    async def ensure_ready(self) -> None:
        async with self._operation():
            await self._prepare()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._operation():
            await self._prepare()
            async with self._connections.get_connection() as connection:
                yield connection

    @asynccontextmanager
    async def ready_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._operation():
            if not self._ready:
                raise TelemetryAnalyticsUnavailable("Telemetry analytics is unavailable")
            async with self._connections.get_connection() as connection:
                yield connection

    async def shutdown(self) -> None:
        await complete_cleanup(self._shutdown())

    async def _shutdown(self) -> None:
        async with self._condition:
            self._closed = True
        if self._sweeper is not None:
            self._sweeper.cancel()
            await asyncio.gather(self._sweeper, return_exceptions=True)
        async with self._condition:
            await self._condition.wait_for(lambda: self._active == 0)
        await self._connections.close()
