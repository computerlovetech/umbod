from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from umbod.core.diagnostics import ApplicationFailureKind

from .ports import UsageRetentionStore


class UsageRetention:
    failure_kind = ApplicationFailureKind.USAGE_RETENTION

    def __init__(
        self, store: UsageRetentionStore, retention_days: int, clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._retention_days = retention_days
        self._clock = clock

    async def run(self) -> None:
        today = self._clock().astimezone(UTC).date()
        await self._store.prune_usage(today - timedelta(days=self._retention_days - 1))
