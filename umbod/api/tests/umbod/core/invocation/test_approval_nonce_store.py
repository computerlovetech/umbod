from tests.persistence_runtime import prepared_inmemory_runtime
from collections.abc import AsyncIterator
from umbod.core.persistence import Database
import asyncio
import pytest
import pytest_asyncio
from umbod.core.invocation import APPROVAL_NONCE_TABLE, ApprovalNonceConsumption, DatabaseApprovalNonceStore

@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        await runtime.database.ensure_schema((APPROVAL_NONCE_TABLE,))
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_nonce_consumption_is_shared_across_store_instances(database: Database) -> None:
    consumption = ApprovalNonceConsumption(nonce='nonce-1', expires_at=1234)
    assert await DatabaseApprovalNonceStore(database).consume(consumption) is True
    assert await DatabaseApprovalNonceStore(database).consume(consumption) is False

@pytest.mark.asyncio
async def test_nonce_concurrent_consumption_has_exactly_one_winner(database: Database) -> None:
    consumption = ApprovalNonceConsumption(nonce='nonce-1', expires_at=1234)
    first = DatabaseApprovalNonceStore(database)
    second = DatabaseApprovalNonceStore(database)
    results = await asyncio.gather(first.consume(consumption), second.consume(consumption))
    assert sorted(results) == [False, True]
