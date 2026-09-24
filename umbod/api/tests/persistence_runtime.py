from pathlib import Path

from umbod.config import (
    InMemoryConnectorStoreConfig,
    PersistenceConfig,
    SQLiteConnectorStoreConfig,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider


def create_persistence_runtime(config: PersistenceConfig) -> PersistenceRuntime:
    return ConfiguredPersistenceRuntimeProvider(config).create()


def create_inmemory_runtime() -> PersistenceRuntime:
    return create_persistence_runtime(InMemoryConnectorStoreConfig())


def create_sqlite_runtime(database_path: Path | str) -> PersistenceRuntime:
    return create_persistence_runtime(
        SQLiteConnectorStoreConfig(sqlite_path=str(database_path))
    )


async def prepared_persistence_runtime(config: PersistenceConfig) -> PersistenceRuntime:
    runtime = create_persistence_runtime(config)
    await runtime.readiness.ensure_ready()
    return runtime


async def prepared_inmemory_runtime() -> PersistenceRuntime:
    return await prepared_persistence_runtime(InMemoryConnectorStoreConfig())


async def prepared_sqlite_runtime(database_path: Path | str) -> PersistenceRuntime:
    return await prepared_persistence_runtime(
        SQLiteConnectorStoreConfig(sqlite_path=str(database_path))
    )
