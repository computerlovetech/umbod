import asyncio

import aiosqlite

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
from umbod.infrastructure.connections import ConnectionProvider
from umbod.infrastructure.persistence.inmemory.database import InMemoryDatabase
from umbod.infrastructure.persistence.schema_preparation import prepare_application_schema
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.factories import create_pooled_sqlite_database
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


class SQLitePersistenceRuntime:
    def __init__(
        self, database: SQLiteDatabase, connections: ConnectionProvider[aiosqlite.Connection]
    ) -> None:
        self.database = database
        self._connections = connections
        self._schema_readiness = SQLitePersistenceReadiness(database)

    @property
    def readiness(self) -> PersistenceReadiness:
        return self

    async def ensure_ready(self) -> None:
        await self._connections.initialize()
        await self._schema_readiness.ensure_ready()

    async def shutdown(self) -> None:
        await self._connections.close()


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
            resources = create_pooled_sqlite_database(
                config.sqlite_path, create_parent_dirs=True
            )
            return SQLitePersistenceRuntime(resources.database, resources.connections)
        assert_never(config)
