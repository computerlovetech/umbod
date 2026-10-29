import sqlite3
from pathlib import Path

import pytest

from tests.umbod.core.downstream_mcp_connectors.test_personal_discovery_event_transactions import Mutation, assert_notification, events, reject_events, snapshot
from tests.umbod.core.downstream_mcp_connectors.test_personal_refresh import command, completion, refresh_store, reservation
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections.models import Authorized
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import FailPersonalRefresh, PersonalRefreshChanged, PersonalRefreshConflict
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_ports import PersonalRefreshStore

__all__ = ["runtime_case", "refresh_store"]
OPERATIONS = ("reserve", "exchange", "release", "fail", "complete", "uncertain")


async def mutation(case: RuntimeCase, store: PersonalRefreshStore, operation: str) -> Mutation:
    if operation == "reserve":
        return lambda: store.reserve(reservation(case))
    await store.reserve(reservation(case))
    if operation == "exchange":
        return lambda: store.exchange(command(case))
    if operation == "release":
        return lambda: store.release(command(case))
    await store.exchange(command(case))
    if operation == "fail":
        return lambda: store.fail(FailPersonalRefresh(**command(case).model_dump(), reason="refresh_denied"))
    if operation == "complete":
        return lambda: store.complete(completion(case))
    if operation == "uncertain":
        invalid = completion(case).model_copy(update={"now": case.query.now.replace(year=2027)})
        return lambda: store.complete(invalid)
    raise AssertionError(operation)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_accepted_refresh_transition_emits_notification(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore, operation: str) -> None:
    run = await mutation(runtime_case, refresh_store, operation)
    before = await events(runtime_case.database)
    if operation == "uncertain":
        with pytest.raises(PersonalRefreshChanged):
            await run()
    else:
        await run()
    assert_notification((await events(runtime_case.database))[len(before):])


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS)
async def test_refresh_event_failure_restores_state_including_uncertainty(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore, tmp_path: Path, operation: str) -> None:
    path = tmp_path / "runtime.sqlite3"
    if not path.exists():
        pytest.skip("SQLite trigger regression")
    run = await mutation(runtime_case, refresh_store, operation)
    before = await snapshot(runtime_case.database)
    previous_events = await events(runtime_case.database)
    reject_events(path)
    with pytest.raises(sqlite3.IntegrityError, match="event append failed"):
        await run()
    assert await snapshot(runtime_case.database) == before
    assert await events(runtime_case.database) == previous_events


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("exchange", "release", "fail", "complete"))
async def test_stale_refresh_commands_publish_nothing(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore, operation: str) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    before = await events(runtime_case.database)
    stale = command(runtime_case).model_copy(update={"claim_id": "stale"})
    if operation == "release":
        await refresh_store.release(stale)
    elif operation == "fail":
        await refresh_store.fail(FailPersonalRefresh(**stale.model_dump(), reason="refresh_denied"))
    else:
        with pytest.raises(PersonalRefreshChanged):
            if operation == "exchange":
                await refresh_store.exchange(stale)
            else:
                await refresh_store.complete(completion(runtime_case).model_copy(update={"claim_id": "stale"}))
    assert await events(runtime_case.database) == before


@pytest.mark.asyncio
async def test_conflicting_reservation_publishes_nothing(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    before = await events(runtime_case.database)
    with pytest.raises(PersonalRefreshConflict):
        await refresh_store.reserve(reservation(runtime_case, "other"))
    assert await events(runtime_case.database) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("fail", "complete"))
async def test_replaced_credentials_prevent_late_refresh_writes_and_notifications(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore, operation: str) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    await install_authorization(runtime_case, Authorized(authorization="replacement-private-token"))
    before = await snapshot(runtime_case.database)
    previous_events = await events(runtime_case.database)
    if operation == "fail":
        await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason="refresh_denied"))
    else:
        with pytest.raises(PersonalRefreshChanged):
            await refresh_store.complete(completion(runtime_case))
    assert await snapshot(runtime_case.database) == before
    assert await events(runtime_case.database) == previous_events
