import asyncio
from collections.abc import Awaitable

import anyio


async def complete_cleanup(operation: Awaitable[None]) -> None:
    task = asyncio.ensure_future(operation)
    cancelled = False
    with anyio.CancelScope(shield=True):
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():
                    raise
                cancelled = True
    if cancelled:
        raise asyncio.CancelledError
