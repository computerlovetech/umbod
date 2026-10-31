import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from .edge import ClientProvider, S3Client

T = TypeVar("T")


async def settle(operation: Awaitable[T], accept: Callable[[T], None]) -> T:
    task = asyncio.ensure_future(operation)
    cancellations: list[asyncio.CancelledError] = []
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancellations.append(error)
        except Exception:
            break
    try:
        result = task.result()
        accept(result)
    except BaseException:
        if cancellations:
            raise cancellations[0] from None
        raise
    if cancellations:
        raise cancellations[0]
    return result


def discard(value: object) -> None:
    pass


async def finish(operation: Awaitable[T]) -> T:
    return await settle(operation, discard)


@asynccontextmanager
async def client_scope(provider: ClientProvider) -> AsyncIterator[S3Client]:
    context = provider()
    opened: list[S3Client] = []
    failed = False
    try:
        client = await settle(context.__aenter__(), opened.append)
        yield client
    except BaseException:
        failed = True
        raise
    finally:
        if opened:
            try:
                await finish(context.__aexit__(None, None, None))
            except BaseException:
                if not failed:
                    raise
