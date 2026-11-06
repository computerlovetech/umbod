from collections.abc import AsyncIterator
from contextlib import AsyncExitStack

import pytest_asyncio


@pytest_asyncio.fixture
async def runtime_resources() -> AsyncIterator[AsyncExitStack]:
    async with AsyncExitStack() as stack:
        yield stack
