from typing import Protocol

from umbod.rest.telemetry.observations import AcceptedCollectorLogs, CompletedCollectorRequest


class CollectorMetricsRecorder(Protocol):
    def record_request(self, event: CompletedCollectorRequest) -> None: ...

    def record_logs(self, event: AcceptedCollectorLogs) -> None: ...
