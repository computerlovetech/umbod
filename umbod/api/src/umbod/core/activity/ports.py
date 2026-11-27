from typing import Protocol, runtime_checkable

from umbod.core.telemetry.analytics.models import TimeRange
from umbod.core.telemetry.analytics.write_models import OwnedLog
from umbod.core.usage.models import OwnedUsageQuery, UsageSummary

from .models import HarnessSummary, MissingSession, SessionDetailQuery, SessionListQuery, SessionReport, SessionSlice


class ActivitySourceUnavailable(Exception):
    pass


class McpActivityReader(Protocol):
    async def summarize(self, query: OwnedUsageQuery) -> UsageSummary: ...


class HarnessActivityReader(Protocol):
    async def summarize(self, owner: OwnedLog, window: TimeRange) -> HarnessSummary: ...

    async def list_sessions(self, query: SessionListQuery) -> SessionSlice: ...

    async def get_session(self, query: SessionDetailQuery) -> SessionReport | MissingSession: ...


@runtime_checkable
class HarnessActivityReaderProvider(Protocol):
    def create_harness_activity_reader(self) -> HarnessActivityReader: ...
