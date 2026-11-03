from dataclasses import dataclass
from typing import Literal

from umbod.core.signals import SignalPublisher


@dataclass(frozen=True)
class CompletedCollectorRequest:
    method: str
    route: Literal["/v1/logs", "/v1/metrics", "/v1/traces"]
    status_class: str
    duration_seconds: float


@dataclass(frozen=True)
class AcceptedCollectorLogs:
    record_count: int


def get_accepted_logs_publisher() -> SignalPublisher[AcceptedCollectorLogs]:
    raise RuntimeError("Collector observations are not installed")
