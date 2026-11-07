from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tests.persistence_runtime import create_inmemory_runtime
from umbod.core.persistence import Database
from umbod.infrastructure.persistence.sqlite.factories import create_unpooled_sqlite_database


def create_contract_sqlite_database(directory: Path) -> Database:
    return create_unpooled_sqlite_database(str(directory / "contract.sqlite"), create_parent_dirs=True)


DatabaseFactory = Callable[[Path], Database]


@dataclass(frozen=True)
class DatabaseAdapter:
    name: str
    factory: DatabaseFactory


def _inmemory(_path: Path) -> Database:
    return create_inmemory_runtime().database


DATABASE_ADAPTERS = (
    DatabaseAdapter('inmemory', _inmemory),
    DatabaseAdapter('sqlite', create_contract_sqlite_database),
)
