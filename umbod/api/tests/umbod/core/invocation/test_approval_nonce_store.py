from tests.persistence_runtime import create_sqlite_runtime
import asyncio
from pathlib import Path
import pytest
from umbod.core.invocation import APPROVAL_NONCE_TABLE, ApprovalNonceConsumption, DatabaseApprovalNonceStore

@pytest.mark.asyncio
async def test_sqlite_nonce_consumption_is_durable_across_store_instances(tmp_path: Path) -> None:
    database = create_sqlite_runtime(tmp_path / 'approval.db').database
    await database.ensure_schema((APPROVAL_NONCE_TABLE,))
    consumption = ApprovalNonceConsumption(nonce='nonce-1', expires_at=1234)
    assert await DatabaseApprovalNonceStore(database).consume(consumption) is True
    assert await DatabaseApprovalNonceStore(database).consume(consumption) is False

@pytest.mark.asyncio
async def test_sqlite_nonce_concurrent_consumption_has_exactly_one_winner(tmp_path: Path) -> None:
    database = create_sqlite_runtime(tmp_path / 'approval.db').database
    await database.ensure_schema((APPROVAL_NONCE_TABLE,))
    consumption = ApprovalNonceConsumption(nonce='nonce-1', expires_at=1234)
    first = DatabaseApprovalNonceStore(database)
    second = DatabaseApprovalNonceStore(database)
    results = await asyncio.gather(first.consume(consumption), second.consume(consumption))
    assert sorted(results) == [False, True]
