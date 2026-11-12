import asyncio
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import pytest

from umbod.config.usage import PersonalUsageConfig
from umbod.core.diagnostics import ApplicationFailure
from umbod.core.usage.models import UsageBatch, UsageKind, UsageOutcome, UsageRecord
from umbod.mcp.usage.statistics import UsageObservations
from umbod.mcp.usage.writer import UsageWriteBehind


class FailureCollector:
    def __init__(self) -> None:
        self.events: list[ApplicationFailure] = []

    def send(self, event: ApplicationFailure) -> None:
        self.events.append(event)


class MemoryUsageWriter:
    def __init__(self) -> None:
        self.batches: list[UsageBatch] = []
        self.pruned: list[date] = []
        self.failures_remaining = 0
        self.blocked = False
        self.attempted = asyncio.Event()
        self.release = asyncio.Event()

    async def append_usage(self, batch: UsageBatch) -> None:
        self.batches.append(batch)
        self.attempted.set()
        if self.blocked:
            await self.release.wait()
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError('SECRET backend failure')

    async def prune_usage(self, before: date) -> None:
        self.pruned.append(before)


@dataclass
class UsageHarness:
    settings: PersonalUsageConfig
    writer: MemoryUsageWriter
    failures: FailureCollector
    delays: list[float]
    runtime: UsageWriteBehind


@pytest.fixture
def harness() -> UsageHarness:
    settings = PersonalUsageConfig(queue_capacity=4, batch_size=2, flush_interval_seconds=0.001,
                                   shutdown_timeout_seconds=0.02, write_timeout_seconds=0.01)
    writer = MemoryUsageWriter()
    failures = FailureCollector()
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    runtime = UsageWriteBehind(settings, writer, UsageObservations(failures, lambda: 0.0),
                              lambda: asyncio.get_running_loop().time(), lambda: 1_735_689_600_000_000_000, sleep)
    return UsageHarness(settings, writer, failures, delays, runtime)


@pytest.fixture
def record() -> UsageRecord:
    return UsageRecord(event_id=UUID(int=1), owner_id='a' * 64,
                       occurred_at_unix_nano=1_735_689_600_000_000_000,
                       observed_at_unix_nano=1_735_689_600_000_000_000,
                       kind=UsageKind.TOOL, outcome=UsageOutcome.SUCCESS,
                       duration_ms=1.0, service_name='test', trace_id='', span_id='')
