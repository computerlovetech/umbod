import asyncio
from collections.abc import Awaitable, Callable

from umbod.core.diagnostics import ApplicationFailureKind
from umbod.core.persistence import Database

from .factory import create_agent_behaviour_service


class DiagnosticRetention:
    failure_kind = ApplicationFailureKind.AGENT_BEHAVIOUR_RETENTION

    def __init__(self, purge: Callable[[], Awaitable[int]]) -> None:
        self._purge = purge

    async def run(self) -> None:
        while await self._purge():
            await asyncio.sleep(0)


def create_diagnostic_retention(database: Database) -> DiagnosticRetention:
    async def purge() -> int:
        return await create_agent_behaviour_service(database).purge_expired()

    return DiagnosticRetention(purge)
