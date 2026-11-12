from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from umbod.core.usage.models import UsageRecord


@dataclass(frozen=True)
class NoUsageCorrelation:
    pass


class UsageCollectionSettings(Protocol):
    enabled: bool
    queue_capacity: int
    max_record_bytes: int
    batch_size: int
    flush_interval_seconds: float
    write_timeout_seconds: float
    max_retries: int
    shutdown_timeout_seconds: float
    retention_days: int


class UsageAdmission(Protocol):
    def enqueue(self, record: UsageRecord) -> None: ...

    def projection_failed(self) -> None: ...


NanosecondClock = Callable[[], int]
MonotonicClock = Callable[[], float]
UsageSleeper = Callable[[float], Awaitable[None]]
