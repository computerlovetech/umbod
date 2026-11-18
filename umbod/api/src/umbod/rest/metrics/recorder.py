from typing import Protocol

from umbod.rest.metrics.models import CompletedRestRequest


class RestMetricsRecorder(Protocol):
    def record_completed_request(self, request: CompletedRestRequest) -> None: ...


class RestMetricsExposer(Protocol):
    def prometheus_text(self) -> bytes: ...


class RestMetricsRecorderExposer(RestMetricsRecorder, RestMetricsExposer, Protocol):
    pass


class RestMetricsServer(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...
