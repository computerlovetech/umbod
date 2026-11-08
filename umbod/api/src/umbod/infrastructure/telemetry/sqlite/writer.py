from pydantic import ValidationError

from umbod.core.telemetry.analytics import (
    LogDimension,
    LogWriteBatch,
    OwnedLog,
    PresentDimensionValue,
    TelemetryAnalyticsUnavailable,
)

from .database import SqliteAnalyticsRuntime
from .values import to_microseconds


class SqliteAnalyticsWriter:
    def __init__(self, runtime: SqliteAnalyticsRuntime) -> None:
        self._runtime = runtime

    async def append_logs(self, batch: LogWriteBatch) -> None:
        try:
            validated = LogWriteBatch.model_validate(batch.model_dump())
        except ValidationError:
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        async with self._runtime.connection() as connection:
            rows = []
            for record in validated.records:
                dimensions = {
                    group.dimension: group.value.value
                    for group in record.dimensions
                    if isinstance(group.value, PresentDimensionValue)
                }
                rows.append(
                    (
                        to_microseconds(record.occurred_at),
                        record.owner.owner_id
                        if isinstance(record.owner, OwnedLog)
                        else None,
                        *(dimensions.get(dimension) for dimension in LogDimension),
                    )
                )
            await connection.execute("BEGIN")
            await connection.executemany(
                "INSERT INTO analytics_logs "
                "(occurred_at_us, owner_id, source, event_name, severity, session_id, tool_name, activity_kind, outcome) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            await connection.commit()
