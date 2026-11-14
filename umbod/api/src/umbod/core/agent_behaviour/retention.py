import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress

from umbod.core.diagnostics import ApplicationFailure, ApplicationFailureKind, NoFailureContext, report_application_failure
from umbod.core.signals import SignalPublisher
from umbod.core.persistence import Database

from .factory import create_agent_behaviour_service


class DiagnosticRetention:
    def __init__(self, purge: Callable[[], Awaitable[int]], application_failures: SignalPublisher[ApplicationFailure], wait: Callable[[float], Awaitable[None]]) -> None:
        self._purge = purge
        self._application_failures = application_failures
        self._wait = wait

    async def _cleanup(self) -> float:
        try:
            async with asyncio.timeout(5):
                while await self._purge():
                    await asyncio.sleep(0)
            return 3600
        except Exception as error:
            report_application_failure(self._application_failures, ApplicationFailureKind.AGENT_BEHAVIOUR_RETENTION, error, NoFailureContext())
            return 60

    async def _run(self, interval: float) -> None:
        while True:
            await self._wait(interval)
            interval = await self._cleanup()

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        interval = await self._cleanup()
        task = asyncio.create_task(self._run(interval), name="agent-behaviour-retention")
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def create_diagnostic_retention(database: Database, application_failures: SignalPublisher[ApplicationFailure]) -> DiagnosticRetention:
    async def purge() -> int:
        return await create_agent_behaviour_service(database).purge_expired()

    return DiagnosticRetention(purge, application_failures, asyncio.sleep)
