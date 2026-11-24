import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import aiosqlite

from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
from umbod.core.telemetry.analytics.backfill import BackfillSelectionLimitExceeded, BackfillWindow
from umbod.core.telemetry.analytics.replay import LogArchiveReplay, ReplayBatch, ReplaySummary
from umbod.infrastructure.connections.lifecycle import complete_cleanup
from umbod.infrastructure.connections.sqlite import open_connection

from .database import validate_path
from .schema import validate_current_schema
from .values import to_microseconds


@asynccontextmanager
async def _archive_operation() -> AsyncIterator[None]:
    try:
        yield
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError, RuntimeError):
        raise TelemetryAnalyticsUnavailable("Telemetry archive backfill is unavailable") from None


@asynccontextmanager
async def open_existing_analytics(
    path: Path, protected_paths: tuple[Path, ...], mode: Literal["ro", "rw"],
) -> AsyncIterator[aiosqlite.Connection]:
    async with _archive_operation():
        resolved_path = validate_path(path, protected_paths)
        connection = aiosqlite.connect(f"{resolved_path.as_uri()}?mode={mode}", uri=True)
        await open_connection(connection)
    try:
        async with _archive_operation():
            await validate_current_schema(connection)
        yield connection
    finally:
        await complete_cleanup(connection.close())


class SqliteLogArchiveBackfill:
    def __init__(
        self, reader: aiosqlite.Connection, cutoff_us: Callable[[], int], replay: LogArchiveReplay,
    ) -> None:
        self._reader = reader
        self._cutoff_us = cutoff_us
        self._replay = replay

    async def select(self, window: BackfillWindow) -> tuple[ReplayBatch, ...]:
        async with _archive_operation():
            async with self._reader.execute(
                "SELECT id FROM analytics_raw_batches "
                "WHERE received_at_us >= ? AND received_at_us < ? AND received_at_us > ? "
                "ORDER BY received_at_us, id LIMIT ?",
                (to_microseconds(window.start), to_microseconds(window.end), self._cutoff_us(), window.limit + 1),
            ) as cursor:
                rows = await cursor.fetchall()
            if len(rows) > window.limit:
                raise BackfillSelectionLimitExceeded("Archive selection exceeds the batch limit")
            return tuple(ReplayBatch(batch_id=row[0]) for row in rows)

    async def preview(self, batch: ReplayBatch) -> ReplaySummary:
        async with _archive_operation():
            return await self._replay.preview(batch)

    async def apply(self, batch: ReplayBatch) -> ReplaySummary:
        async with _archive_operation():
            return await self._replay.apply(batch)
