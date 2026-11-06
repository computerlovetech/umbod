from dataclasses import dataclass

import aiosqlite

from umbod.infrastructure.connections import (
    ConnectionPool,
    ConnectionProvider,
    UnpooledConnectionProvider,
)
from umbod.infrastructure.connections.sqlite import SQLiteConnectionDriver

from .database import SQLiteDatabase


@dataclass(frozen=True)
class SQLiteDatabaseResources:
    database: SQLiteDatabase
    connections: ConnectionProvider[aiosqlite.Connection]


def create_pooled_sqlite_database(
    database_path: str, *, create_parent_dirs: bool
) -> SQLiteDatabaseResources:
    driver = SQLiteConnectionDriver(database_path, create_parent_dirs=create_parent_dirs)
    connections = ConnectionPool(driver, size=1 if database_path == ":memory:" else 2)
    return SQLiteDatabaseResources(SQLiteDatabase(connections), connections)


def create_unpooled_sqlite_database(
    database_path: str, *, create_parent_dirs: bool
) -> SQLiteDatabase:
    driver = SQLiteConnectionDriver(database_path, create_parent_dirs=create_parent_dirs)
    connections = UnpooledConnectionProvider(driver.connect, driver.close)
    return SQLiteDatabase(connections)
