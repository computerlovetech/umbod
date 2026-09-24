import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorDiscoveryScheduleOptions:
    refresh_interval_seconds: float
    jitter_ratio: float
    maximum_backoff_seconds: float


class ConnectorDiscoverySchedule:
    def __init__(
        self,
        options: ConnectorDiscoveryScheduleOptions,
        monotonic_clock: Callable[[], float],
        random_source: Callable[[], float],
    ) -> None:
        self._options = options
        self._clock = monotonic_clock
        self._random = random_source
        self._next_due: dict[str, float] = {}
        self._failures: dict[str, int] = {}

    def is_due(self, connector_id: str, now: float) -> bool:
        return self._next_due.get(connector_id, 0) <= now

    def record_success(self, connector_id: str) -> None:
        self._failures.pop(connector_id, None)
        self._schedule(connector_id, self._options.refresh_interval_seconds)

    def record_failure(self, connector_id: str) -> int:
        failures = self._failures.get(connector_id, 0) + 1
        self._failures[connector_id] = failures
        delay = min(
            self._options.maximum_backoff_seconds,
            self._options.refresh_interval_seconds * (2 ** (failures - 1)),
        )
        self._schedule(connector_id, delay)
        return failures

    def forget(self, connector_id: str) -> None:
        self._next_due.pop(connector_id, None)
        self._failures.pop(connector_id, None)

    def now(self) -> float:
        return self._clock()

    def _schedule(self, connector_id: str, delay: float) -> None:
        jitter = delay * self._options.jitter_ratio * ((self._random() * 2) - 1)
        self._next_due[connector_id] = self._clock() + max(0, delay + jitter)


class PeriodicDiscoveryRunner:
    def __init__(
        self,
        refresh_interval_seconds: float,
        refresh_configured: Callable[[bool], Awaitable[None]],
    ) -> None:
        self._refresh_interval_seconds = refresh_interval_seconds
        self._refresh_configured = refresh_configured
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        self._stopped.clear()
        await self._refresh_configured(True)
        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._refresh_interval_seconds)
            except TimeoutError:
                await self._refresh_configured(False)

    def stop(self) -> None:
        self._stopped.set()
