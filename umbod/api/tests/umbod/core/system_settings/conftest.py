from collections.abc import AsyncIterator

import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.persistence import Database


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()
