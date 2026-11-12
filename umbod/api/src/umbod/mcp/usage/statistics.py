from dataclasses import dataclass
from enum import StrEnum

from umbod.core.diagnostics import ApplicationFailure, ApplicationFailureKind, NoFailureContext
from umbod.core.signals import SignalPublisher

from .ports import MonotonicClock


class UsageDropReason(StrEnum):
    PROJECTION = 'projection_failed'
    OVERSIZED = 'oversized'
    OVERFLOW = 'overflow'
    WRITE = 'retries_exhausted'
    SHUTDOWN = 'shutdown_loss'


_FAILURE_KINDS = {
    UsageDropReason.PROJECTION: ApplicationFailureKind.USAGE_PROJECTION,
    UsageDropReason.OVERSIZED: ApplicationFailureKind.USAGE_OVERSIZED,
    UsageDropReason.OVERFLOW: ApplicationFailureKind.USAGE_OVERFLOW,
    UsageDropReason.WRITE: ApplicationFailureKind.USAGE_WRITE,
    UsageDropReason.SHUTDOWN: ApplicationFailureKind.USAGE_SHUTDOWN,
}
_COUNTER_LIMIT = 2**63 - 1


@dataclass(frozen=True)
class UsageStatistics:
    accepted: int
    persisted: int
    dropped: tuple[tuple[UsageDropReason, int], ...]


class UsageObservations:
    def __init__(self, failures: SignalPublisher[ApplicationFailure], monotonic: MonotonicClock) -> None:
        self._failures = failures
        self._monotonic = monotonic
        self._accepted = 0
        self._persisted = 0
        self._dropped = dict.fromkeys(UsageDropReason, 0)
        self._last_notification: dict[ApplicationFailureKind, float] = {}

    @property
    def statistics(self) -> UsageStatistics:
        return UsageStatistics(self._accepted, self._persisted, tuple(self._dropped.items()))

    def accept(self) -> None:
        self._accepted = min(_COUNTER_LIMIT, self._accepted + 1)

    def persist(self, count: int) -> None:
        self._persisted = min(_COUNTER_LIMIT, self._persisted + count)

    def drop(self, reason: UsageDropReason, count: int) -> None:
        if count == 0:
            return
        self._dropped[reason] = min(_COUNTER_LIMIT, self._dropped[reason] + count)
        self.failure(_FAILURE_KINDS[reason])

    def failure(self, kind: ApplicationFailureKind) -> None:
        now = self._monotonic()
        previous = self._last_notification.get(kind)
        if previous is not None and now - previous < 60:
            return
        self._last_notification[kind] = now
        _, component, operation, reason = kind.value
        event = ApplicationFailure(
            kind=kind,
            attributes=(('event.name', 'application.failure'), ('component', component),
                        ('operation', operation), ('reason', reason), ('outcome', 'failure')),
            correlation=NoFailureContext(),
        )
        try:
            self._failures.send(event)
        except Exception:
            return
