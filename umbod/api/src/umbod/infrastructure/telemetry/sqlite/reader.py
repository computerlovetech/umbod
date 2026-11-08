from pydantic import ValidationError

from umbod.core.telemetry.analytics import (
    BucketWidth,
    DimensionGroup,
    FixedTimeBuckets,
    LogCountQuery,
    LogCountResult,
    LogCountRow,
    LogDimension,
    MissingDimensionValue,
    OwnersScope,
    PresentDimensionValue,
    TimeBucket,
    TelemetryAnalyticsUnavailable,
    Unbucketed,
)

from .database import SqliteAnalyticsRuntime
from .values import from_microseconds, to_microseconds

IDENTIFIERS = {dimension: dimension.value for dimension in LogDimension}
WIDTHS = {
    BucketWidth.MINUTE: 60000000,
    BucketWidth.HOUR: 3600000000,
    BucketWidth.DAY: 86400000000,
}


class SqliteAnalyticsReader:
    def __init__(self, runtime: SqliteAnalyticsRuntime) -> None:
        self._runtime = runtime

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        try:
            query = LogCountQuery.model_validate(query.model_dump())
        except ValidationError:
            raise TelemetryAnalyticsUnavailable(
                "Telemetry analytics is unavailable"
            ) from None
        async with self._runtime.connection() as connection:
            columns = []
            if isinstance(query.bucketing, FixedTimeBuckets):
                width = WIDTHS[query.bucketing.width]
                columns.append(
                    f"(occurred_at_us - ((occurred_at_us % {width} + {width}) % {width})) AS bucket"
                )
            columns.extend(
                IDENTIFIERS[dimension] + " COLLATE BINARY"
                for dimension in query.group_by
            )
            predicates = ["occurred_at_us >= ?", "occurred_at_us < ?"]
            parameters: list[int | str] = [
                to_microseconds(query.time_range.start),
                to_microseconds(query.time_range.end),
            ]
            if isinstance(query.scope, OwnersScope):
                predicates.append(
                    "owner_id COLLATE BINARY IN ("
                    + ",".join("?" for _ in query.scope.owner_ids)
                    + ")"
                )
                parameters.extend(query.scope.owner_ids)
            for item in query.filters:
                predicates.append(
                    IDENTIFIERS[item.dimension]
                    + " COLLATE BINARY IN ("
                    + ",".join("?" for _ in item.values)
                    + ")"
                )
                parameters.extend(item.values)
            selection = ", ".join([*columns, "COUNT(*)"])
            statement = (
                "SELECT "
                + selection
                + " FROM analytics_logs WHERE "
                + " AND ".join(predicates)
            )
            if columns:
                positions = ", ".join(str(index + 1) for index in range(len(columns)))
                statement += " GROUP BY " + positions + " ORDER BY " + positions
            statement += " LIMIT ? OFFSET ?"
            parameters.extend((query.pagination.limit + 1, query.pagination.offset))
            async with connection.execute(statement, parameters) as cursor:
                records = await cursor.fetchall()
            has_more = len(records) > query.pagination.limit
            rows = []
            for record in records[:query.pagination.limit]:
                bucketed = isinstance(query.bucketing, FixedTimeBuckets)
                offset = int(bucketed)
                groups = tuple(
                    DimensionGroup(
                        dimension=dimension,
                        value=MissingDimensionValue(kind="missing")
                        if record[index + offset] is None
                        else PresentDimensionValue(
                            kind="present", value=record[index + offset]
                        ),
                    )
                    for index, dimension in enumerate(query.group_by)
                )
                rows.append(
                    LogCountRow(
                        groups=groups,
                        count=record[-1],
                        bucket=TimeBucket(
                            kind="bucket", start=from_microseconds(record[0])
                        )
                        if bucketed
                        else Unbucketed(kind="none"),
                    )
                )
            return LogCountResult(rows=tuple(rows), has_more=has_more)
