from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_oauth_attempt_persistence import AttemptCase, CompletionWriteFailureCipher, case, claim_command, publication
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_attempts import EncryptedPersonalOAuthAttemptStore
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import AbsentPersonalRefreshToken, ExpiringPersonalToken, PersonalOAuthGrant, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthQuery, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.models import ReplacePersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import CompletePersonalOAuthAttempt, FailPersonalOAuthAttempt
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery

__all__ = ["case"]


@pytest.mark.asyncio
async def test_failed_completion_transaction_restores_rejection_and_connection(case: AttemptCase) -> None:
    prepared = await authorized_attempt_case(case)
    original = await prepared.bundle.personal_connections.get(prepared.query.key)
    await prepared.bundle.personal_runtime_authorizations.reject_authorization(RejectPersonalAuthorization(key=original.key, expected_connection_revision=original.revision))
    await prepared.store.reserve(prepared.command)
    await prepared.store.publish(publication(prepared))
    await prepared.store.claim(claim_command(prepared))
    failing = EncryptedPersonalOAuthAttemptStore(prepared.database, CompletionWriteFailureCipher(), prepared.clock)
    with pytest.raises(RuntimeError, match="simulated completion write failure"):
        await failing.complete(CompletePersonalOAuthAttempt(query=prepared.query, claim_id="exclusive-claim", authorization=original.authorization))
    assert await prepared.bundle.personal_connections.get(original.key) == original
    assert (await prepared.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=original.key, now=prepared.query.now))).state == "reconnect_required"
    assert (await prepared.store.get(prepared.query)).status == "exchanging"


async def authorized_attempt_case(case: AttemptCase) -> AttemptCase:
    grant = PersonalOAuthGrant(
        version=2, key=case.query.key, issuer="https://issuer.example", resource=case.command.endpoint_url,
        client_id="client", token_endpoint="https://issuer.example/token", redirect_uri=case.command.preparation.redirect_uri,
        client_mode="dynamic_public", token_endpoint_auth_method="none", requested_scopes=(), granted_scopes=(),
        configuration_revision="legacy", issued_at=case.query.now, lifetime=ExpiringPersonalToken(expires_at=case.query.now + timedelta(hours=1)),
        access_token=SecretStr("saved-token"), refresh_token=AbsentPersonalRefreshToken(),
    )
    connection = await case.bundle.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=case.query.key, expected_revision=case.command.expected_revision, authorization=authorize_personal_grant(grant)))
    return replace(case, command=case.command.model_copy(update={"expected_revision": connection.revision}))


@pytest.mark.asyncio
@pytest.mark.parametrize("identical", [True, False])
async def test_interactive_completion_rotates_revision_clears_marker_and_ignores_late_rejection(case: AttemptCase, identical: bool) -> None:
    prepared = await authorized_attempt_case(case)
    original = await prepared.bundle.personal_connections.get(prepared.query.key)
    rejected = RejectPersonalAuthorization(key=original.key, expected_connection_revision=original.revision)
    await prepared.bundle.personal_runtime_authorizations.reject_authorization(rejected)
    await prepared.store.reserve(prepared.command)
    await prepared.store.publish(publication(prepared))
    await prepared.store.claim(claim_command(prepared))
    authorization = original.authorization
    if not identical:
        raw = authorization.authorization.get_secret_value().replace("saved-token", "new-token")
        authorization = authorization.model_copy(update={"authorization": SecretStr(raw)})
    await prepared.store.complete(CompletePersonalOAuthAttempt(query=prepared.query, claim_id="exclusive-claim", authorization=authorization))
    current = await prepared.bundle.personal_connections.get(original.key)
    assert current.revision != original.revision
    assert current.authorization == authorization
    await prepared.bundle.personal_runtime_authorizations.reject_authorization(rejected)
    result = await prepared.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=original.key, now=prepared.query.now))
    assert result.state == "authorized"
    target = await prepared.bundle.personal_runtime_authorizations.resolve(PersonalRuntimeAuthorizationQuery(key=original.key, group_ids=("team",), now=prepared.query.now))
    assert target.authorization_revision == current.revision


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["pending", "failed", "cancelled"])
async def test_unsuccessful_reconnect_retains_rejection(case: AttemptCase, outcome: str) -> None:
    prepared = await authorized_attempt_case(case)
    original = await prepared.bundle.personal_connections.get(prepared.query.key)
    await prepared.bundle.personal_runtime_authorizations.reject_authorization(RejectPersonalAuthorization(key=original.key, expected_connection_revision=original.revision))
    await prepared.store.reserve(prepared.command)
    await prepared.store.publish(publication(prepared))
    if outcome == "failed":
        await prepared.store.claim(claim_command(prepared))
        await prepared.store.fail(FailPersonalOAuthAttempt(query=prepared.query, claim_id="exclusive-claim"))
    elif outcome == "cancelled":
        await prepared.store.cancel(prepared.query)
    assert await prepared.bundle.personal_connections.get(original.key) == original
    assert (await prepared.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=original.key, now=prepared.query.now))).state == "reconnect_required"
