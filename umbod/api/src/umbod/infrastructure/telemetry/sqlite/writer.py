import aiosqlite
from pydantic import ValidationError

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    ArchivedLogWriteBatch,
    LogAppendBatch,
    LogDimension,
    LogWriteBatch,
    OwnedLog,
    PresentDimensionValue,
    TelemetryAnalyticsUnavailable,
)

from .database import SqliteAnalyticsRuntime
from .values import to_microseconds


class UnlinkedLogRows:
    pass


class SqliteAnalyticsWriter:
    def __init__(self, runtime: SqliteAnalyticsRuntime) -> None:
        self._runtime = runtime

    async def append_logs(self, batch: LogAppendBatch) -> None:
        try:
            validated = (
                ArchivedLogWriteBatch.model_validate(batch.model_dump(warnings=False))
                if isinstance(batch, ArchivedLogWriteBatch)
                else LogWriteBatch.model_validate(batch.model_dump())
            )
        except ValidationError:
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        async with self._runtime.connection() as connection:
            await connection.execute("BEGIN")
            batch_id = (
                await _insert_raw_batch(connection, validated)
                if isinstance(validated, ArchivedLogWriteBatch)
                else UnlinkedLogRows()
            )
            await insert_log_rows(connection, validated.records, batch_id)
            await connection.commit()


async def insert_log_rows(
    connection: aiosqlite.Connection, records: tuple[AnalyticsLogRecord, ...], link: int | UnlinkedLogRows,
) -> None:
    batch_id = link if isinstance(link, int) else None
    rows = []
    for index, record in enumerate(records):
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
                record.normalization.model_dump_json()
                if record.normalization.kind == "normalized"
                else None,
                batch_id,
                index if batch_id is not None else None,
            )
        )
    async with connection.executemany(
        "INSERT INTO analytics_logs "
        "(occurred_at_us, owner_id, source, event_name, severity, session_id, "
        "tool_name, activity_kind, outcome, normalization_json, raw_batch_id, raw_record_index) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    ) as cursor:
        if cursor.rowcount != len(rows):
            raise ValueError("Incomplete analytics writes")


async def _insert_raw_batch(
    connection: aiosqlite.Connection, batch: ArchivedLogWriteBatch,
) -> int:
    async with connection.execute(
        "INSERT INTO analytics_raw_batches (raw_payload, encoding, received_at_us, owner_id) "
        "VALUES (?, ?, ?, ?)",
        (
            batch.raw_payload,
            batch.encoding,
            to_microseconds(batch.received_at),
            batch.owner.owner_id if isinstance(batch.owner, OwnedLog) else None,
        ),
    ) as cursor:
        if cursor.rowcount != 1 or cursor.lastrowid is None:
            raise ValueError("Incomplete analytics archive write")
        return cursor.lastrowid
