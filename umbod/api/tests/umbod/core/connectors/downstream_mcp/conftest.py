from collections.abc import AsyncIterator

import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.personal_oauth_cases import AttemptCase, initialized_attempt_case
from tests.support.personal_runtime_cases import RuntimeCase, _create_runtime_case


@pytest_asyncio.fixture
async def discovery_runtime_case() -> AsyncIterator[RuntimeCase]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield await _create_runtime_case(runtime.database)
    finally:
        await runtime.shutdown()


@pytest_asyncio.fixture
async def oauth_completion_case() -> AsyncIterator[AttemptCase]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield await initialized_attempt_case(runtime.database)
    finally:
        await runtime.shutdown()
