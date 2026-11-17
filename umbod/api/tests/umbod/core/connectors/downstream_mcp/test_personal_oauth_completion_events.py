import pytest

from tests.support.personal_discovery_events import assert_notification, events, reject_events, rollback_snapshot
from tests.support.personal_oauth_cases import AttemptCase, claim_command, completion, pending
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthUnavailable

@pytest.mark.asyncio
async def test_oauth_direct_connection_completion_emits_one_notification(oauth_completion_case: AttemptCase) -> None:
    await pending(oauth_completion_case)
    await oauth_completion_case.store.claim(claim_command(oauth_completion_case))
    before = await events(oauth_completion_case.database)
    await oauth_completion_case.store.complete(completion(oauth_completion_case))
    assert_notification((await events(oauth_completion_case.database))[len(before):])


@pytest.mark.asyncio
async def test_oauth_completion_event_failure_restores_connection_and_attempt(oauth_completion_case: AttemptCase, monkeypatch: pytest.MonkeyPatch) -> None:
    await pending(oauth_completion_case)
    await oauth_completion_case.store.claim(claim_command(oauth_completion_case))
    before = await rollback_snapshot(oauth_completion_case.database)
    previous_events = await events(oauth_completion_case.database)
    reject_events(oauth_completion_case.database, monkeypatch)
    with pytest.raises(RuntimeError, match="event append failed"):
        await oauth_completion_case.store.complete(completion(oauth_completion_case))
    assert await rollback_snapshot(oauth_completion_case.database) == before
    assert await events(oauth_completion_case.database) == previous_events
    assert (await oauth_completion_case.store.get(oauth_completion_case.query)).status == "exchanging"


@pytest.mark.asyncio
async def test_stale_oauth_completion_emits_nothing(oauth_completion_case: AttemptCase) -> None:
    await pending(oauth_completion_case)
    await oauth_completion_case.store.claim(claim_command(oauth_completion_case))
    before = await events(oauth_completion_case.database)
    with pytest.raises(PersonalOAuthUnavailable):
        await oauth_completion_case.store.complete(completion(oauth_completion_case).model_copy(update={"claim_id": "stale"}))
    assert await events(oauth_completion_case.database) == before


@pytest.mark.asyncio
async def test_attempt_history_deletion_emits_nothing(oauth_completion_case: AttemptCase) -> None:
    await pending(oauth_completion_case)
    before = await events(oauth_completion_case.database)
    await oauth_completion_case.store.delete_connector("personal")
    assert await events(oauth_completion_case.database) == before
