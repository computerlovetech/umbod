import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite

from .lifecycle import complete_cleanup


async def open_connection(connection: aiosqlite.Connection) -> None:
    stop = connection.stop
    stopping: list[asyncio.Future[object]] = []

    def stop_once() -> Optional[asyncio.Future[object]]:
        if stopping:
            return stopping[0]
        future = stop()
        if future is not None:
            stopping.append(future)
        return future

    connection.stop = stop_once
    opening = asyncio.ensure_future(connection)
    try:
        try:
            await asyncio.shield(opening)
        except BaseException:
            async def close_opened_connection() -> None:
                try:
                    await asyncio.gather(opening, return_exceptions=True)
                finally:
                    try:
                        await connection.close()
                    finally:
                        if stopping:
                            await stopping[0]

            await complete_cleanup(close_opened_connection())
            raise
    finally:
        connection.stop = stop


class SQLiteConnectionDriver:
    def __init__(self, database_path: str, *, create_parent_dirs: bool) -> None:
        self._database_path = database_path
        self._create_parent_dirs = create_parent_dirs

    async def connect(self) -> aiosqlite.Connection:
        if self._create_parent_dirs:
            Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = aiosqlite.connect(self._database_path)
        await open_connection(connection)
        try:
            connection.row_factory = aiosqlite.Row
            for statement in ("PRAGMA foreign_keys=ON", "PRAGMA busy_timeout=5000"):
                cursor = await connection.execute(statement)
                await cursor.close()
            return connection
        except BaseException:
            await complete_cleanup(connection.close())
            raise

    async def reset(self, connection: aiosqlite.Connection) -> None:
        await connection.rollback()
        cursor = await connection.execute("PRAGMA query_only=OFF")
        await cursor.close()
        connection.row_factory = aiosqlite.Row

    async def close(self, connection: aiosqlite.Connection) -> None:
        await connection.close()
