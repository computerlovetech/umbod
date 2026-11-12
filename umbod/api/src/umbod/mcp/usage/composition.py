import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from umbod.config import AppConfig
from umbod.core.diagnostics import ApplicationFailure
from umbod.core.persistence import Database
from umbod.core.signals import SignalPublisher
from umbod.core.usage.store import DatabaseUsageStore
from umbod.mcp.signals import McpSignals

from .receivers import CapabilityUsageReceiver, InvocationUsageReceiver, UsageCompletionProjection
from .statistics import UsageObservations, UsageStatistics
from .writer import UsageWriteBehind


class McpUsageRuntime:
    def __init__(self, writer: UsageWriteBehind) -> None:
        self._writer = writer

    @property
    def statistics(self) -> UsageStatistics:
        return self._writer.statistics

    @property
    def running(self) -> bool:
        return self._writer.running

    def start(self) -> None:
        self._writer.start()

    async def stop(self) -> None:
        await self._writer.stop()

    @asynccontextmanager
    async def lifespan(self, server: FastMCP) -> AsyncIterator[dict[str, object]]:
        self.start()
        try:
            yield {}
        finally:
            await self.stop()


def create_mcp_usage_runtime(
    settings: AppConfig, database: Database, signals: McpSignals,
    application_failures: SignalPublisher[ApplicationFailure],
) -> McpUsageRuntime:
    observations = UsageObservations(application_failures, time.monotonic)
    writer = UsageWriteBehind(
        settings.personal_usage, DatabaseUsageStore(database), observations,
        time.monotonic, time.time_ns, asyncio.sleep,
    )
    if settings.personal_usage.enabled:
        for signal, name in (
            (signals.invocation_completed, 'mcp.invocation.usage'),
            (signals.capability_completed, 'mcp.capability.usage'),
        ):
            if signal.is_connected(name):
                raise ValueError('Usage receivers already registered')
        projection = UsageCompletionProjection(writer, settings.runtime.app_name, time.time_ns)
        signals.invocation_completed.connect('mcp.invocation.usage', InvocationUsageReceiver(projection))
        signals.capability_completed.connect('mcp.capability.usage', CapabilityUsageReceiver(projection))
    return McpUsageRuntime(writer)
