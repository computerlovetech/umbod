import sqlite3
from pathlib import Path

import pytest

from tests.umbod.core.downstream_mcp_connectors.test_personal_discovery_event_transactions import assert_notification, events, reject_events, snapshot
from tests.umbod.core.downstream_mcp_connectors.test_personal_oauth_attempt_persistence import AttemptCase, case, claim_command, completion, pending
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthUnavailable

__all__ = ["case"]


@pytest.mark.asyncio
async def test_oauth_direct_connection_completion_emits_one_notification(case: AttemptCase) -> None:
    await pending(case)
    await case.store.claim(claim_command(case))
    before = await events(case.database)
    await case.store.complete(completion(case))
    assert_notification((await events(case.database))[len(before):])


@pytest.mark.asyncio
async def test_oauth_completion_event_failure_restores_connection_and_attempt(case: AttemptCase, tmp_path: Path) -> None:
    path = tmp_path / "oauth.sqlite3"
    if not path.exists():
        pytest.skip("SQLite trigger regression")
    await pending(case)
    await case.store.claim(claim_command(case))
    before = await snapshot(case.database)
    previous_events = await events(case.database)
    reject_events(path)
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        await case.store.complete(completion(case))
    assert await snapshot(case.database) == before
    assert await events(case.database) == previous_events
    assert (await case.store.get(case.query)).status == "exchanging"


@pytest.mark.asyncio
async def test_stale_oauth_completion_emits_nothing(case: AttemptCase) -> None:
    await pending(case)
    await case.store.claim(claim_command(case))
    before = await events(case.database)
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.complete(completion(case).model_copy(update={"claim_id": "stale"}))
    assert await events(case.database) == before


@pytest.mark.asyncio
async def test_attempt_history_deletion_emits_nothing(case: AttemptCase) -> None:
    await pending(case)
    before = await events(case.database)
    await case.store.delete_connector("personal")
    assert await events(case.database) == before
