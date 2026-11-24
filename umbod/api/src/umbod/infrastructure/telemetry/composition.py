from pathlib import Path

from umbod.config.app import AppConfig
from umbod.config.telemetry import TelemetryAppConfig
from umbod.core.telemetry.analytics import (
    ArchivedLogWriteBatch,
    LogAppendBatch,
    LogCountQuery,
    LogCountResult,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
)


class DisabledTelemetryAnalyticsRuntime:
    async def ensure_ready(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def create_reader(self) -> TelemetryAnalyticsReader:
        return self

    def create_writer(self) -> TelemetryAnalyticsWriter:
        return self

    async def append_logs(self, batch: LogAppendBatch) -> None:
        if isinstance(batch, ArchivedLogWriteBatch):
            raise TelemetryAnalyticsUnavailable("Telemetry analytics is disabled")

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        raise TelemetryAnalyticsUnavailable("Telemetry analytics is disabled")


def create_configured_analytics_runtime(config: AppConfig | TelemetryAppConfig) -> TelemetryAnalyticsRuntime:
    if not config.telemetry_analytics.enabled:
        return create_disabled_analytics_runtime()
    from .sqlite.database import SqliteAnalyticsRuntime
    from .sqlite.retention import utc_now

    return SqliteAnalyticsRuntime.with_retention(
        Path(config.telemetry_analytics.sqlite_path),
        analytics_protected_paths(config),
        config.telemetry_analytics.raw_archive_retention_days,
        utc_now,
    )


def analytics_protected_paths(config: AppConfig | TelemetryAppConfig) -> tuple[Path, ...]:
    if not isinstance(config, AppConfig) or config.connector_store.type != "sqlite":
        return ()
    application_path = config.connector_store.sqlite_path
    if application_path == ":memory:":
        return ()
    if (
        not application_path.strip()
        or application_path.strip().lower().startswith("file:")
        or "\x00" in application_path
    ):
        raise ValueError("Analytics cannot protect an unsafe application database path")
    return (Path(application_path),)


def create_disabled_analytics_runtime() -> TelemetryAnalyticsRuntime:
    return DisabledTelemetryAnalyticsRuntime()


def create_sqlite_analytics_runtime(
    database_path: Path, protected_paths: tuple[Path, ...]
) -> TelemetryAnalyticsRuntime:
    from .sqlite.database import SqliteAnalyticsRuntime

    return SqliteAnalyticsRuntime(database_path, protected_paths)
