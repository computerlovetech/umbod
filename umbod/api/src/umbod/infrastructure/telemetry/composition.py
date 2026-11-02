from pathlib import Path

from umbod.config.app import AppConfig
from umbod.core.telemetry.analytics import (
    LogCountQuery,
    LogCountResult,
    LogWriteBatch,
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

    async def append_logs(self, batch: LogWriteBatch) -> None:
        return None

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        raise TelemetryAnalyticsUnavailable("Telemetry analytics is disabled")


def create_configured_analytics_runtime(config: AppConfig) -> TelemetryAnalyticsRuntime:
    if not config.telemetry_analytics.enabled:
        return create_disabled_analytics_runtime()
    protected_paths: tuple[Path, ...] = ()
    if config.connector_store.type == "sqlite":
        application_path = config.connector_store.sqlite_path
        if application_path == ":memory:":
            protected_paths = ()
        elif (
            not application_path.strip()
            or application_path.strip().lower().startswith("file:")
            or "\x00" in application_path
        ):
            raise ValueError(
                "Analytics cannot protect an unsafe application database path"
            )
        else:
            protected_paths = (Path(application_path),)
    return create_sqlite_analytics_runtime(
        Path(config.telemetry_analytics.sqlite_path), protected_paths
    )


def create_disabled_analytics_runtime() -> TelemetryAnalyticsRuntime:
    return DisabledTelemetryAnalyticsRuntime()


def create_sqlite_analytics_runtime(
    database_path: Path, protected_paths: tuple[Path, ...]
) -> TelemetryAnalyticsRuntime:
    from .sqlite.database import SqliteAnalyticsRuntime

    return SqliteAnalyticsRuntime(database_path, protected_paths)
