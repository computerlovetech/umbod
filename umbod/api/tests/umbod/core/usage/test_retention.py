from datetime import date, datetime

import pytest

from umbod.core.usage.retention import UsageRetention


class RetentionStore:
    def __init__(self) -> None:
        self.cutoffs: list[date] = []

    async def prune_usage(self, before: date) -> None:
        self.cutoffs.append(before)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "now,days,cutoff",
    [
        ("2025-01-01T00:00:00+00:00", 90, date(2024, 10, 4)),
        ("2025-01-01T00:01:00+02:00", 1, date(2024, 12, 31)),
        ("2024-12-31T23:59:00-02:00", 1, date(2025, 1, 1)),
    ],
)
async def test_one_shot_prunes_using_utc_inclusive_retention_window(now: str, days: int, cutoff: date) -> None:
    store = RetentionStore()
    await UsageRetention(store, days, lambda: datetime.fromisoformat(now)).run()
    assert store.cutoffs == [cutoff]
