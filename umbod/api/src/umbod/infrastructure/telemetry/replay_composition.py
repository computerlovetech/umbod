from umbod.core.telemetry.adapters.otlp_normalization import normalize_archived_logs
from umbod.core.telemetry.analytics import TelemetryAnalyticsRuntime, TelemetryAnalyticsUnavailable
from umbod.core.telemetry.analytics.replay import LogArchiveReplay, ReplayNormalizer

from .sqlite.database import SqliteAnalyticsRuntime
from .sqlite.replay import SqliteReplayArchive


def create_log_archive_replay(runtime: TelemetryAnalyticsRuntime) -> LogArchiveReplay:
    return create_log_archive_replay_with_normalizer(runtime, normalize_archived_logs)


def create_log_archive_replay_with_normalizer(
    runtime: TelemetryAnalyticsRuntime, normalizer: ReplayNormalizer,
) -> LogArchiveReplay:
    if not isinstance(runtime, SqliteAnalyticsRuntime):
        raise TelemetryAnalyticsUnavailable("Telemetry archive replay is unavailable")
    store = SqliteReplayArchive(runtime.ready_connection, runtime.ready_connection, runtime.archive_cutoff_us)
    return LogArchiveReplay(store, normalizer)
