from datetime import timedelta

import pytest
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, install_authorization, runtime_case
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate, DownstreamConnectorUnitOfWorkService, utc_clock
from umbod.core.connectors.downstream_mcp.stores.personal_connections import EncryptedPersonalConnectionStore
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import UnknownPersonalTokenLifetime, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthQuery, PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.models import Authorized, CanonicalPrincipal, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.personal_authorization_health_schema import PERSONAL_AUTHORIZATION_REJECTION_TABLE
from umbod.core.persistence import AllFields, NoFilter, Query, TransactionMode, Unordered

__all__ = ["runtime_case"]


class DisconnectWriteFailureCipher:
    def encrypt(self, plaintext: str) -> str:
        raise RuntimeError("injected disconnect write failure")

    def decrypt(self, ciphertext: str) -> str:
        return AuthenticatedTextCipher("runtime-secret").decrypt(ciphertext)


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["disconnect", "delete"])
async def test_cleanup_failure_rolls_back_marker_removal(runtime_case: RuntimeCase, cleanup: str) -> None:
    await reject_current(runtime_case)
    original = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    if cleanup == "disconnect":
        store = EncryptedPersonalConnectionStore(runtime_case.database, DisconnectWriteFailureCipher())
        with pytest.raises(RuntimeError, match="injected disconnect"):
            await store.disconnect(runtime_case.query.key)
    else:
        def failing_phase(phase: str) -> None:
            if phase == "credential":
                raise RuntimeError("injected aggregate delete failure")
        unit = DownstreamConnectorUnitOfWorkService(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), failing_phase, utc_clock)
        with pytest.raises(RuntimeError, match="injected aggregate"):
            await unit.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    assert await runtime_case.bundle.personal_connections.get(runtime_case.query.key) == original
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == "reconnect_required"


def health_query(case: RuntimeCase) -> PersonalAuthorizationHealthQuery:
    return PersonalAuthorizationHealthQuery(key=case.query.key, now=case.query.now)


async def reject_current(case: RuntimeCase) -> RejectPersonalAuthorization:
    target = await case.store.resolve(case.query)
    command = RejectPersonalAuthorization(key=target.key, expected_connection_revision=target.authorization_revision)
    await case.store.reject_authorization(command)
    return command


@pytest.mark.asyncio
async def test_local_health_does_not_require_enablement_publication_tools_or_groups(runtime_case: RuntimeCase) -> None:
    await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
    await runtime_case.bundle.publishing.unpublish_connector("personal")
    result = await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))
    assert result.state == "authorized"
    assert set(result.model_dump()) == {"state", "expires_at", "refresh_supported"}
    assert "owner" not in result.model_dump_json()
    assert "https" not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("change,expected", [("expired", "expired"), ("unknown", "unsupported"), ("future", "unsupported"), ("binding", "unsupported"), ("legacy", "unsupported"), ("malformed", "unsupported")])
async def test_health_classifies_only_validated_saved_facts(runtime_case: RuntimeCase, change: str, expected: str) -> None:
    grant = runtime_case.grant
    if change == "expired":
        grant = grant.model_copy(update={"issued_at": runtime_case.query.now - timedelta(hours=2), "lifetime": grant.lifetime.model_copy(update={"expires_at": runtime_case.query.now})})
    elif change == "unknown":
        grant = grant.model_copy(update={"lifetime": UnknownPersonalTokenLifetime()})
    elif change == "future":
        grant = grant.model_copy(update={"issued_at": runtime_case.query.now + timedelta(seconds=1)})
    elif change == "binding":
        grant = grant.model_copy(update={"resource": "https://different.example/mcp"})
    authorization = authorize_personal_grant(grant)
    if change in {"legacy", "malformed"}:
        authorization = Authorized(authorization=SecretStr('{"access_token":"legacy"}' if change == "legacy" else "malformed"))
    await install_authorization(runtime_case, authorization)
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == expected


@pytest.mark.asyncio
async def test_absence_and_owners_are_explicit(runtime_case: RuntimeCase) -> None:
    other = runtime_case.query.key.model_copy(update={"principal": CanonicalPrincipal(namespace="trusted", subject="other")})
    result = await runtime_case.bundle.personal_authorization_health.get(PersonalAuthorizationHealthQuery(key=other, now=runtime_case.query.now))
    assert result.model_dump() == {"state": "not_authorized"}


@pytest.mark.asyncio
async def test_rejection_is_durable_and_does_not_rotate_or_remove_credentials(runtime_case: RuntimeCase) -> None:
    previous = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    await reject_current(runtime_case)
    recreated = await create_downstream_mcp_stores("runtime-secret", runtime_case.database)
    health = await recreated.personal_authorization_health.get(health_query(runtime_case))
    assert health.model_dump() == {"state": "reconnect_required", "reason": "provider_rejected"}
    assert await recreated.personal_connections.get(runtime_case.query.key) == previous
    with pytest.raises(PersonalRuntimeUnavailable):
        await recreated.personal_runtime_authorizations.resolve(runtime_case.query)
    expired_query = health_query(runtime_case).model_copy(update={"now": runtime_case.query.now + timedelta(hours=2)})
    assert (await recreated.personal_authorization_health.get(expired_query)).state == "reconnect_required"


@pytest.mark.asyncio
async def test_recorded_rejection_survives_enablement_revision_changes(runtime_case: RuntimeCase) -> None:
    await reject_current(runtime_case)
    for enabled in (False, True):
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=enabled))
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == "reconnect_required"
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
async def test_full_authorization_fingerprint_not_only_access_token_controls_rejection(runtime_case: RuntimeCase) -> None:
    command = await reject_current(runtime_case)
    grant = runtime_case.grant.model_copy(update={"granted_scopes": ("read", "write")})
    await install_authorization(runtime_case, authorize_personal_grant(grant))
    await runtime_case.store.reject_authorization(command)
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == "authorized"
    assert (await runtime_case.store.resolve(runtime_case.query)).access_token == runtime_case.grant.access_token


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["disconnect", "delete"])
async def test_cleanup_removes_marker_and_late_reports_cannot_resurrect(runtime_case: RuntimeCase, cleanup: str) -> None:
    command = await reject_current(runtime_case)
    if cleanup == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    else:
        await runtime_case.bundle.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    await runtime_case.store.reject_authorization(command)
    async with runtime_case.database.session(mode=TransactionMode.READ_WRITE) as session:
        records = await session.find_many(PERSONAL_AUTHORIZATION_REJECTION_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    assert records == () or records == []
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == "not_authorized"


@pytest.mark.asyncio
async def test_wrong_cipher_is_operational_failure_not_unsupported(runtime_case: RuntimeCase) -> None:
    recreated = await create_downstream_mcp_stores("wrong-secret", runtime_case.database)
    with pytest.raises(PersonalAuthorizationHealthUnavailable) as caught:
        await recreated.personal_authorization_health.get(health_query(runtime_case))
    assert caught.value.__context__ is None
    assert str(caught.value) == "Personal authorization health unavailable"


@pytest.mark.asyncio
async def test_marker_payload_is_encrypted(runtime_case: RuntimeCase) -> None:
    await reject_current(runtime_case)
    async with runtime_case.database.session(mode=TransactionMode.READ_WRITE) as session:
        records = await session.find_many(PERSONAL_AUTHORIZATION_REJECTION_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
    assert len(records) == 1
    assert "credential_fingerprint" not in records[0].document
    decoded = AuthenticatedTextCipher("runtime-secret").decrypt(records[0].document)
    assert "credential_fingerprint" in decoded
    assert "owner-token" not in decoded
