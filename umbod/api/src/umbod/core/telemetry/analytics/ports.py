from typing import Protocol

from .models import LogCountQuery, LogCountResult
from .write_models import LogWriteBatch


class TelemetryAnalyticsReader(Protocol):
    async def count_logs(self, query: LogCountQuery) -> LogCountResult: ...


class TelemetryAnalyticsWriter(Protocol):
    async def append_logs(self, batch: LogWriteBatch) -> None: ...


class TelemetryAnalyticsRuntime(Protocol):
    async def ensure_ready(self) -> None: ...

    async def shutdown(self) -> None: ...

    def create_reader(self) -> TelemetryAnalyticsReader: ...

    def create_writer(self) -> TelemetryAnalyticsWriter: ...
