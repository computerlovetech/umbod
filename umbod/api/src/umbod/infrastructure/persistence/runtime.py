import asyncio
from dataclasses import dataclass
from typing import assert_never

from umbod.config import (
    InMemoryConnectorStoreConfig,
    PersistenceConfig,
    SQLiteConnectorStoreConfig,
)
from umbod.core.persistence import (
    Database,
    PersistenceReadiness,
    PersistenceRuntime,
)
from umbod.infrastructure.persistence.inmemory.database import InMemoryDatabase
from umbod.infrastructure.persistence.schema_preparation import prepare_application_schema
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.schema_preparation import SQLiteCurrentSchemaPreparation


class _IdempotentReadiness:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._ready = False

    async def ensure_ready(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            await self._prepare()
            self._ready = True

    async def _prepare(self) -> None:
        raise NotImplementedError


class InMemoryPersistenceReadiness(_IdempotentReadiness):
    def __init__(self, database: InMemoryDatabase) -> None:
        super().__init__()
        self._database = database

    async def _prepare(self) -> None:
        await prepare_application_schema(self._database)


class SQLitePersistenceReadiness(_IdempotentReadiness):
    def __init__(self, database: SQLiteDatabase) -> None:
        super().__init__()
        self._database = database

    async def _prepare(self) -> None:
        await SQLiteCurrentSchemaPreparation(self._database).execute()


@dataclass(frozen=True)
class AppPersistenceRuntime:
    database: Database
    readiness: PersistenceReadiness

    async def shutdown(self) -> None:
        return None


class ConfiguredPersistenceRuntimeProvider:
    def __init__(self, config: PersistenceConfig) -> None:
        self._config = config

    def create(self) -> PersistenceRuntime:
        config = self._config
        if isinstance(config, InMemoryConnectorStoreConfig):
            database = InMemoryDatabase()
            return AppPersistenceRuntime(
                database=database,
                readiness=InMemoryPersistenceReadiness(database),
            )
        if isinstance(config, SQLiteConnectorStoreConfig):
            database = SQLiteDatabase(config.sqlite_path, create_parent_dirs=True)
            return AppPersistenceRuntime(
                database=database,
                readiness=SQLitePersistenceReadiness(database),
            )
        assert_never(config)
