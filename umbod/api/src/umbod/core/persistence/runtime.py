from typing import Protocol

from umbod.core.persistence.ports import Database


class PersistenceReadiness(Protocol):
    async def ensure_ready(self) -> None: ...


class PersistenceRuntime(Protocol):
    @property
    def database(self) -> Database: ...

    @property
    def readiness(self) -> PersistenceReadiness: ...

    async def shutdown(self) -> None: ...


class PersistenceRuntimeProvider(Protocol):
    def create(self) -> PersistenceRuntime: ...
