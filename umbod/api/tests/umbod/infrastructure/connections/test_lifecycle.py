import asyncio

import anyio
import pytest

from umbod.infrastructure.connections.lifecycle import complete_cleanup

pytestmark = pytest.mark.asyncio


async def test_cleanup_operation_failure_propagates() -> None:
    async def fail() -> None:
        raise ValueError("cleanup failed")

    with pytest.raises(ValueError, match="cleanup failed"):
        await asyncio.wait_for(complete_cleanup(fail()), 2)


async def test_cleanup_operation_cancellation_propagates_without_retrying() -> None:
    async def cancel() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(complete_cleanup(cancel()), 2)


async def test_anyio_cancelled_scope_still_finishes_cleanup() -> None:
    finished = asyncio.Event()

    async def cleanup() -> None:
        await anyio.lowlevel.checkpoint()
        finished.set()

    with anyio.CancelScope() as scope:
        scope.cancel()
        await complete_cleanup(cleanup())
    assert finished.is_set()
