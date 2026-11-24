from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from umbod.config.app import AppConfig
from umbod.core.telemetry.adapters.otlp_normalization import normalize_archived_logs
from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
from umbod.core.telemetry.analytics.backfill import LogArchiveBackfillStore
from umbod.core.telemetry.analytics.replay import LogArchiveReplay

from .composition import analytics_protected_paths
from .sqlite.backfill import SqliteLogArchiveBackfill, open_existing_analytics
from .sqlite.replay import SqliteReplayArchive
from .sqlite.retention import archive_cutoff_us, utc_now


@asynccontextmanager
async def create_log_archive_backfill(config: AppConfig, *, apply: bool) -> AsyncIterator[LogArchiveBackfillStore]:
    settings = config.telemetry_analytics
    if not settings.enabled:
        raise TelemetryAnalyticsUnavailable("Telemetry analytics is disabled")
    path = Path(settings.sqlite_path)
    protected_paths = analytics_protected_paths(config)

    def cutoff_us() -> int:
        return archive_cutoff_us(utc_now(), settings.raw_archive_retention_days)

    async with open_existing_analytics(path, protected_paths, "ro") as reader:
        @asynccontextmanager
        async def read_connection() -> AsyncIterator[aiosqlite.Connection]:
            yield reader

        @asynccontextmanager
        async def write_connection() -> AsyncIterator[aiosqlite.Connection]:
            if not apply:
                raise TelemetryAnalyticsUnavailable("Telemetry archive backfill is read-only")
            async with open_existing_analytics(path, protected_paths, "rw") as writer:
                yield writer

        archive = SqliteReplayArchive(read_connection, write_connection, cutoff_us)
        replay = LogArchiveReplay(archive, normalize_archived_logs)
        yield SqliteLogArchiveBackfill(reader, cutoff_us, replay)
