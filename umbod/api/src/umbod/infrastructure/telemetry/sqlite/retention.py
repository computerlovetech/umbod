from datetime import datetime, timezone

import aiosqlite

from .values import to_microseconds


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def archive_cutoff_us(now: datetime, retention_days: int) -> int:
    return to_microseconds(now) - retention_days * 86_400_000_000


async def expire_raw_archives(
    connection: aiosqlite.Connection, cutoff_us: int,
) -> None:
    if cutoff_us < -(2**63):
        return
    cursor = await connection.execute(
        "DELETE FROM analytics_raw_batches WHERE received_at_us <= ?", (cutoff_us,),
    )
    await cursor.close()
    await connection.commit()
