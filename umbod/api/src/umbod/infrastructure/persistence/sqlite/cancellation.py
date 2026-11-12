from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Event

import aiosqlite

from umbod.infrastructure.connections.lifecycle import complete_cleanup


async def _rollback_and_clear_progress(connection: aiosqlite.Connection, failed: bool) -> None:
    await connection.set_progress_handler(None, 0)
    if failed or connection.in_transaction:
        await connection.rollback()


@asynccontextmanager
async def interruptible_transaction(connection: aiosqlite.Connection) -> AsyncIterator[None]:
    cancelled = Event()
    failed = False
    try:
        await connection.set_progress_handler(cancelled.is_set, 1000)
        yield
    except BaseException:
        failed = True
        cancelled.set()
        await complete_cleanup(connection.interrupt())
        raise
    finally:
        await complete_cleanup(_rollback_and_clear_progress(connection, failed))
