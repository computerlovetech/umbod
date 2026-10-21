import asyncio
from uuid import uuid4
from datetime import timedelta

import pytest
import pytest_asyncio
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from tests.umbod.core.downstream_mcp_connectors.test_personal_authorization_health import DisconnectWriteFailureCipher
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.stores.personal_connections import EncryptedPersonalConnectionStore
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import ExpiringPersonalToken, PresentPersonalRefreshToken, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthQuery, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.models import SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import ClaimPersonalOAuthAttempt, CompletePersonalOAuthAttempt, PersonalOAuthAttemptQuery, PersonalOAuthConflict, PreparePersonalOAuth, PreparedPersonalOAuth, PublishPersonalOAuthAttempt, ReservePersonalOAuthAttempt
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_attempts import EncryptedPersonalOAuthAttemptStore
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import CompletePersonalRefresh, FailPersonalRefresh, PersonalRefreshChanged, PersonalRefreshCommand, PersonalRefreshConflict, PersonalRefreshReconnectRequired, PersonalRefreshUnsupported, ReservePersonalRefresh
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_ports import PersonalRefreshStore
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.stores.personal_refresh import EncryptedPersonalRefreshStore
from umbod.core.connectors.downstream_mcp.stores.personal_refresh_schema import PERSONAL_REFRESH_TABLE
from umbod.core.persistence import AllFields, NoFilter, Query, TransactionMode, Unordered

__all__ = ["runtime_case"]


@pytest_asyncio.fixture
async def refresh_store(runtime_case: RuntimeCase) -> PersonalRefreshStore:
    grant = runtime_case.grant.model_copy(update={"refresh_token": PresentPersonalRefreshToken(token=SecretStr("refresh-sentinel"))})
    await install_authorization(runtime_case, authorize_personal_grant(grant))
    return EncryptedPersonalRefreshStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)


def reservation(case: RuntimeCase, claim_id: str = "claim") -> ReservePersonalRefresh:
    return ReservePersonalRefresh(key=case.query.key, group_ids=case.query.group_ids, claim_id=claim_id, now=case.query.now)


def command(case: RuntimeCase) -> PersonalRefreshCommand:
    return PersonalRefreshCommand(key=case.query.key, claim_id="claim", now=case.query.now)


def completion(case: RuntimeCase) -> CompletePersonalRefresh:
    grant = case.grant.model_copy(update={"refresh_token": PresentPersonalRefreshToken(token=SecretStr("rotated-sentinel")), "access_token": SecretStr("new-token"), "lifetime": ExpiringPersonalToken(expires_at=case.query.now + timedelta(hours=2))})
    return CompletePersonalRefresh(**command(case).model_dump(), authorization=authorize_personal_grant(grant))


@pytest.mark.asyncio
async def test_refresh_claim_excludes_parallel_workers_and_blocks_new_runtime(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    results = await asyncio.gather(refresh_store.reserve(reservation(runtime_case)), refresh_store.reserve(reservation(runtime_case, "other")), return_exceptions=True)
    assert sum(isinstance(result, PersonalRefreshConflict) for result in results) == 1
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)
    health = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=runtime_case.query.key, now=runtime_case.query.now))
    assert health.state == "refreshing"
    assert set(health.model_dump()) == {"state", "deadline"}


@pytest.mark.asyncio
@pytest.mark.parametrize("phase,expected", [("preparing", "authorized"), ("exchanging", "reconnect_required")])
async def test_expired_health_projection_does_not_mutate_or_reclaim_claim(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, phase: str, expected: str) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    if phase == "exchanging":
        await refresh_store.exchange(command(runtime_case))
    async with runtime_case.database.session(mode=TransactionMode.READ_WRITE) as session:
        before = await session.find_many(PERSONAL_REFRESH_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    query = PersonalAuthorizationHealthQuery(key=runtime_case.query.key, now=runtime_case.query.now + timedelta(seconds=31))
    assert (await runtime_case.bundle.personal_authorization_health.get(query)).state == expected
    async with runtime_case.database.session(mode=TransactionMode.READ_WRITE) as session:
        after = await session.find_many(PERSONAL_REFRESH_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    assert before == after
    assert "refresh-sentinel" not in before[0].document
    assert "credential_fingerprint" not in before[0].document


@pytest.mark.asyncio
async def test_identical_refresh_authorization_still_forces_fresh_revision(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    original = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    await refresh_store.complete(CompletePersonalRefresh(**command(runtime_case).model_dump(), authorization=original.authorization))
    current = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    assert current.authorization == original.authorization
    assert current.revision != original.revision


@pytest.mark.asyncio
async def test_rotated_refresh_installs_atomically_and_always_changes_revision(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    old = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    recreated: PersonalRefreshStore = EncryptedPersonalRefreshStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)
    await recreated.complete(completion(runtime_case))
    current = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    assert current.revision != old.revision
    assert current.authorization == completion(runtime_case).authorization
    assert (await runtime_case.store.resolve(runtime_case.query)).access_token.get_secret_value() == "new-token"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["refresh_uncertain", "refresh_denied"])
async def test_terminal_failure_survives_restart_and_enablement_changes(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, status: str) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    for enabled in (False, True):
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=enabled))
    await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason=status))
    recreated: PersonalRefreshStore = EncryptedPersonalRefreshStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)
    with pytest.raises(PersonalRefreshReconnectRequired):
        await recreated.reserve(reservation(runtime_case, "next"))
    health = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=runtime_case.query.key, now=runtime_case.query.now))
    assert health.model_dump() == {"state": "reconnect_required", "reason": status}


@pytest.mark.asyncio
async def test_failed_install_after_enablement_race_retains_uncertainty(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    for enabled in (False, True):
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=enabled))
    with pytest.raises(PersonalRefreshChanged):
        await refresh_store.complete(completion(runtime_case))
    with pytest.raises(PersonalRefreshReconnectRequired):
        await refresh_store.reserve(reservation(runtime_case, "next"))


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["preparing", "exchanging"])
async def test_expired_claim_is_only_reclaimable_before_exchange(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, phase: str) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    if phase == "exchanging":
        await refresh_store.exchange(command(runtime_case))
    later = reservation(runtime_case, "next").model_copy(update={"now": runtime_case.query.now + timedelta(seconds=31)})
    if phase == "exchanging":
        with pytest.raises(PersonalRefreshReconnectRequired):
            await refresh_store.reserve(later)
    else:
        await refresh_store.reserve(later)
        with pytest.raises(PersonalRefreshChanged):
            await refresh_store.exchange(command(runtime_case))


@pytest.mark.asyncio
async def test_provider_rejection_during_refresh_is_never_cleared(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    old = await runtime_case.store.resolve(runtime_case.query)
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    await runtime_case.store.reject_authorization(RejectPersonalAuthorization(key=old.key, expected_connection_revision=old.authorization_revision))
    with pytest.raises(PersonalRefreshChanged):
        await refresh_store.complete(completion(runtime_case))
    health = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=old.key, now=runtime_case.query.now))
    assert health.model_dump() == {"state": "reconnect_required", "reason": "provider_rejected"}


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["disconnect", "delete"])
async def test_cleanup_clears_claim_and_ignores_late_failure(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, cleanup: str) -> None:
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    if cleanup == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    else:
        await runtime_case.bundle.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason="refresh_uncertain"))
    with pytest.raises(PersonalRefreshChanged):
        await refresh_store.complete(completion(runtime_case))
    async with runtime_case.database.session(mode=TransactionMode.READ_WRITE) as session:
        rows = await session.find_many(PERSONAL_REFRESH_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    assert not rows


@pytest.mark.asyncio
async def test_disconnect_write_failure_rolls_back_claim_removal(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    original = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    connections = EncryptedPersonalConnectionStore(runtime_case.database, DisconnectWriteFailureCipher())
    with pytest.raises(RuntimeError, match="injected disconnect"):
        await connections.disconnect(runtime_case.query.key)
    assert await runtime_case.bundle.personal_connections.get(runtime_case.query.key) == original
    with pytest.raises(PersonalRefreshConflict):
        await refresh_store.reserve(reservation(runtime_case, "next"))


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["scope", "resource", "expiry", "client"])
async def test_invalid_provider_result_preserves_old_grant_and_blocks_reuse(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, change: str) -> None:
    old = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    claim = await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    updates = {"scope": {"granted_scopes": ("read", "write")}, "resource": {"resource": "https://other.example/mcp"}, "expiry": {"lifetime": ExpiringPersonalToken(expires_at=runtime_case.query.now)}, "client": {"client_id": "other"}}[change]
    bad = CompletePersonalRefresh(**command(runtime_case).model_dump(), authorization=authorize_personal_grant(claim.grant.model_copy(update=updates)))
    with pytest.raises(PersonalRefreshChanged):
        await refresh_store.complete(bad)
    assert await runtime_case.bundle.personal_connections.get(runtime_case.query.key) == old
    with pytest.raises(PersonalRefreshReconnectRequired):
        await refresh_store.reserve(reservation(runtime_case, "next"))


@pytest.mark.asyncio
async def test_expired_access_token_can_refresh_without_network_discovery(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    grant = runtime_case.grant.model_copy(update={"refresh_token": PresentPersonalRefreshToken(token=SecretStr("refresh-sentinel")), "lifetime": ExpiringPersonalToken(expires_at=runtime_case.query.now)})
    await install_authorization(runtime_case, authorize_personal_grant(grant))
    health = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=runtime_case.query.key, now=runtime_case.query.now))
    assert health.state == "expired" and health.refresh_supported
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    await refresh_store.complete(completion(runtime_case))


@pytest.mark.asyncio
async def test_absent_refresh_token_is_unsupported(runtime_case: RuntimeCase) -> None:
    store: PersonalRefreshStore = EncryptedPersonalRefreshStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)
    with pytest.raises(PersonalRefreshUnsupported):
        await store.reserve(reservation(runtime_case))


async def oauth_reservation(case: RuntimeCase, refresh_store: PersonalRefreshStore) -> ReservePersonalOAuthAttempt:
    claim = await refresh_store.reserve(reservation(case))
    await refresh_store.release(command(case))
    attempt_id = uuid4().hex
    return ReservePersonalOAuthAttempt(key=claim.key, attempt_id=attempt_id, expected_revision=claim.expected_revision, definition_fingerprint=claim.definition_fingerprint, endpoint_url=claim.grant.resource, group_ids=claim.group_ids, preparation=PreparePersonalOAuth(endpoint_url=claim.grant.resource, redirect_uri=claim.grant.redirect_uri, state=SecretStr(attempt_id + ".secret-state"), code_verifier=SecretStr("verifier"), policy=claim.policy), created_at=case.query.now, expires_at=case.query.now + timedelta(minutes=5))


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["refresh", "oauth"])
async def test_refresh_and_interactive_oauth_reservations_exclude_each_other(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, first: str) -> None:
    oauth = await oauth_reservation(runtime_case, refresh_store)
    attempts = EncryptedPersonalOAuthAttemptStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)
    if first == "refresh":
        await refresh_store.reserve(reservation(runtime_case))
        with pytest.raises(PersonalOAuthConflict):
            await attempts.reserve(oauth)
    else:
        await attempts.reserve(oauth)
        with pytest.raises(PersonalRefreshConflict):
            await refresh_store.reserve(reservation(runtime_case))


@pytest.mark.asyncio
@pytest.mark.parametrize("late", ["success", "failure"])
async def test_successful_identical_oauth_clears_refresh_atomically_and_fences_late_worker(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase, late: str) -> None:
    oauth = await oauth_reservation(runtime_case, refresh_store)
    original = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason="refresh_uncertain"))
    attempts = EncryptedPersonalOAuthAttemptStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)
    await attempts.reserve(oauth)
    query = PersonalOAuthAttemptQuery(key=oauth.key, attempt_id=oauth.attempt_id, now=runtime_case.query.now)
    await attempts.publish(PublishPersonalOAuthAttempt(query=query, prepared=PreparedPersonalOAuth(authorization_url=SecretStr("https://issuer.example/authorize"), context=SecretStr("context"))))
    await attempts.claim(ClaimPersonalOAuthAttempt(state=oauth.preparation.state, claim_id="oauth-claim", now=runtime_case.query.now))
    await attempts.complete(CompletePersonalOAuthAttempt(query=query, claim_id="oauth-claim", authorization=original.authorization))
    if late == "success":
        with pytest.raises(PersonalRefreshChanged):
            await refresh_store.complete(completion(runtime_case))
    else:
        await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason="refresh_uncertain"))
    current = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    assert current.authorization == original.authorization
    assert current.revision != original.revision
    assert (await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=oauth.key, now=runtime_case.query.now))).state == "authorized"


@pytest.mark.asyncio
async def test_failed_or_cancelled_oauth_retains_refresh_uncertainty(refresh_store: PersonalRefreshStore, runtime_case: RuntimeCase) -> None:
    oauth = await oauth_reservation(runtime_case, refresh_store)
    await refresh_store.reserve(reservation(runtime_case))
    await refresh_store.exchange(command(runtime_case))
    await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason="refresh_uncertain"))
    attempts = EncryptedPersonalOAuthAttemptStore(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), lambda: runtime_case.query.now)
    await attempts.reserve(oauth)
    await attempts.cancel(PersonalOAuthAttemptQuery(key=oauth.key, attempt_id=oauth.attempt_id, now=runtime_case.query.now))
    with pytest.raises(PersonalRefreshReconnectRequired):
        await refresh_store.reserve(reservation(runtime_case, "next"))
