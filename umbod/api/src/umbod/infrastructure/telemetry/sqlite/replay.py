from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import aiosqlite

from umbod.core.telemetry.analytics import OwnedLog, UnownedLog
from umbod.core.telemetry.analytics.replay import (
    ReplayArchiveUnavailable,
    ReplayBatch,
    ReplayProjection,
    ReplaySummary,
    replay_summary,
)
from umbod.core.telemetry.analytics.write_models import LogArchiveSource

from .values import from_microseconds, to_microseconds
from .writer import insert_log_rows


ReplayConnection = Callable[[], AbstractAsyncContextManager[aiosqlite.Connection]]


class SqliteReplayArchive:
    def __init__(
        self, read_connection: ReplayConnection, write_connection: ReplayConnection,
        archive_cutoff_us: Callable[[], int],
    ) -> None:
        self._read_connection = read_connection
        self._write_connection = write_connection
        self._archive_cutoff_us = archive_cutoff_us

    async def read(self, batch: ReplayBatch) -> LogArchiveSource:
        async with self._read_connection() as connection:
            return await self._load(connection, batch)

    async def replace(self, batch: ReplayBatch, project: ReplayProjection) -> ReplaySummary:
        async with self._write_connection() as connection:
            async with connection.execute("BEGIN IMMEDIATE"):
                pass
            source = await self._load(connection, batch)
            projection = project(source)
            summary = replay_summary(batch, projection)
            async with connection.execute(
                "DELETE FROM analytics_logs WHERE raw_batch_id = ?", (batch.batch_id,),
            ):
                pass
            await insert_log_rows(connection, projection.records, batch.batch_id)
            self._check_expiry(to_microseconds(source.received_at))
            await connection.commit()
            return summary

    async def _load(
        self, connection: aiosqlite.Connection, batch: ReplayBatch,
    ) -> LogArchiveSource:
        async with connection.execute(
            "SELECT raw_payload, encoding, received_at_us, owner_id "
            "FROM analytics_raw_batches WHERE id = ? AND received_at_us > ?",
            (batch.batch_id, self._archive_cutoff_us()),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ReplayArchiveUnavailable("Archived log batch is unavailable")
        raw_payload, encoding, received_at_us, owner_id = row
        self._check_expiry(received_at_us)
        return LogArchiveSource(
            raw_payload=raw_payload,
            encoding=encoding,
            received_at=from_microseconds(received_at_us),
            owner=UnownedLog(kind="unowned") if owner_id is None else OwnedLog(kind="owned", owner_id=owner_id),
        )

    def _check_expiry(self, received_at_us: int) -> None:
        if received_at_us <= self._archive_cutoff_us():
            raise ReplayArchiveUnavailable("Archived log batch is unavailable")
