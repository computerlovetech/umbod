import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from umbod.core.telemetry.analytics import (
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
)

from .schema import ensure_schema


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
        try:
            self._path = validate_path(database_path, protected_paths)
            self._protected_paths = tuple(path.absolute() for path in protected_paths)
        except (OSError, RuntimeError):
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        self._condition = asyncio.Condition()
        self._readiness_lock = asyncio.Lock()
        self._ready = False
        self._closed = False
        self._active = 0

    def create_reader(self) -> TelemetryAnalyticsReader:
        from .reader import SqliteAnalyticsReader

        return SqliteAnalyticsReader(self)

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
        except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError):
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify_all()

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = aiosqlite.connect(self._path, timeout=5.0)
        opening = asyncio.ensure_future(connection)
        try:
            await asyncio.shield(opening)
            await connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            try:
                await opening
            finally:
                await connection.close()

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
                await preparing
            async with self._connection() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                await ensure_schema(connection)
                await connection.commit()
                async with connection.execute("PRAGMA journal_mode = WAL") as cursor:
                    journal_mode = (await cursor.fetchone())[0]
                if journal_mode != "wal":
                    raise ValueError("Analytics requires WAL journal mode")
            self._ready = True

    async def ensure_ready(self) -> None:
        async with self._operation():
            await self._prepare()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._operation():
            await self._prepare()
            async with self._connection() as connection:
                yield connection

    async def shutdown(self) -> None:
        async with self._condition:
            self._closed = True
            await self._condition.wait_for(lambda: self._active == 0)
