import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from umbod.config import load_server_app_config
from umbod.core.telemetry.analytics import (
    DimensionFilter,
    InstanceScope,
    LogCountQuery,
    LogDimension,
    NoTimeBuckets,
    OwnersScope,
    TimeRange,
)
from umbod.infrastructure import create_configured_analytics_runtime


async def verify_analytics() -> None:
    config = load_server_app_config(".env")
    analytics_path = Path(config.telemetry_analytics.sqlite_path).resolve()
    application_path = Path(config.connector_store.sqlite_path).resolve()
    assert analytics_path != application_path
    runtime = create_configured_analytics_runtime(config)
    try:
        await runtime.ensure_ready()
        query = LogCountQuery(
            scope=InstanceScope(kind="instance"),
            time_range=TimeRange(
                start=datetime(1970, 1, 1, tzinfo=timezone.utc),
                end=datetime(3000, 1, 1, tzinfo=timezone.utc),
            ),
            filters=(DimensionFilter(dimension=LogDimension.SOURCE, values=("umbod-otlp-runtime",)),),
            group_by=(LogDimension.SOURCE,),
            bucketing=NoTimeBuckets(kind="none"),
            max_groups=10,
        )
        reader = runtime.create_reader()
        result = await reader.count_logs(query)
        assert len(result.rows) == 1
        assert result.rows[0].count == 2
        owner_query = LogCountQuery.model_validate(query.model_dump() | {
            "scope": OwnersScope(kind="owners", owner_ids=("untrusted-client",)),
        })
        assert (await reader.count_logs(owner_query)).rows == ()
    finally:
        await runtime.shutdown()
    connection = sqlite3.connect(application_path.as_uri() + "?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'analytics_logs'"
        ).fetchall() == []
    finally:
        connection.close()


if __name__ == "__main__":
    asyncio.run(verify_analytics())
