from typing import Protocol

from umbod.core.diagnostics import ApplicationFailureKind


class CleanupJob(Protocol):
    @property
    def failure_kind(self) -> ApplicationFailureKind: ...

    async def run(self) -> None: ...
