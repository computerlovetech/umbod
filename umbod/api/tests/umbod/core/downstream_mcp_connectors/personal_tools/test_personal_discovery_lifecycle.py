import json
from datetime import timedelta

import pytest

from tests.umbod.core.downstream_mcp_connectors.personal_discovery_support import read_available
from tests.umbod.core.downstream_mcp_connectors.test_personal_refresh import command, completion, refresh_store, reservation
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, replace_policy, save_matches
from umbod.core.configuration.persistence import AuthenticatedTextCipher, TextCipher
from umbod.core.connectors.downstream_mcp.personal_connections import SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import PersonalOAuthGrant, authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import RejectPersonalAuthorization
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import CompletePersonalRefresh, FailPersonalRefresh, PersonalRefreshChanged
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_ports import PersonalRefreshStore
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery, PersonalOAuthSettings, PreconfiguredPublicOAuthClient, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.stores.personal_connections import DefinitionBoundPersonalConnectionStore

__all__ = ["runtime_case", "refresh_store"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["preparing", "exchanging", "refresh_uncertain", "refresh_denied", "complete", "invalid_complete", "release"])
async def test_refresh_projection_tracks_every_transition_and_preparing_deadline(runtime_case: RuntimeCase, refresh_store: PersonalRefreshStore, phase: str) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    assert len(await read_available(runtime_case.bundle, runtime_case.query)) == 1
    await refresh_store.reserve(reservation(runtime_case))
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()
    if phase == "release":
        await refresh_store.release(command(runtime_case))
    elif phase != "preparing":
        await refresh_store.exchange(command(runtime_case))
        if phase in ("refresh_uncertain", "refresh_denied"):
            await refresh_store.fail(FailPersonalRefresh(**command(runtime_case).model_dump(), reason=phase))
        elif phase == "complete":
            await refresh_store.complete(completion(runtime_case))
        elif phase == "invalid_complete":
            invalid = completion(runtime_case)
            grant = PersonalOAuthGrant.model_validate_json(invalid.authorization.authorization.get_secret_value()).model_copy(update={"resource": "https://different.example/mcp"})
            with pytest.raises(PersonalRefreshChanged):
                await refresh_store.complete(CompletePersonalRefresh(**invalid.model_dump(exclude={"authorization"}), authorization=authorize_personal_grant(grant)))
    later = runtime_case.query.model_copy(update={"now": runtime_case.query.now + timedelta(seconds=31)})
    assert bool(await read_available(runtime_case.bundle, later)) is (phase in ("preparing", "release"))


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["reject", "replace_configuration", "delete_configuration"])
async def test_rejection_and_configuration_invalidation_remove_availability(runtime_case: RuntimeCase, mutation: str) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    if mutation == "reject":
        connection = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
        await runtime_case.bundle.personal_tool_access.reject_authorization(RejectPersonalAuthorization(key=runtime_case.query.key, expected_connection_revision=connection.revision))
    elif mutation == "delete_configuration":
        await runtime_case.bundle.personal_oauth_configurations.delete_connector("personal")
    else:
        configuration = await runtime_case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
        settings = PersonalOAuthSettings(requested_scopes=("different",), client=PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example", client_id="client"))
        await runtime_case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=settings))
    assert await read_available(runtime_case.bundle, runtime_case.query) == ()


class ProjectionWriteFailureCipher:
    def __init__(self, delegate: TextCipher) -> None:
        self._delegate = delegate

    def encrypt(self, plaintext: str) -> str:
        if json.loads(plaintext).get("kind") in ("available", "unavailable"):
            raise RuntimeError("projection write failed")
        return self._delegate.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        return self._delegate.decrypt(ciphertext)


@pytest.mark.asyncio
async def test_projection_write_failure_rolls_back_connection_and_inventory_availability(runtime_case: RuntimeCase) -> None:
    await save_matches(runtime_case, await replace_policy(runtime_case, (approved_tool("read"),)))
    previous = await read_available(runtime_case.bundle, runtime_case.query)
    connection = await runtime_case.bundle.personal_connections.get(runtime_case.query.key)
    store = DefinitionBoundPersonalConnectionStore(runtime_case.database, ProjectionWriteFailureCipher(AuthenticatedTextCipher("runtime-secret")))
    with pytest.raises(RuntimeError, match="projection write failed"):
        await store.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
    assert await runtime_case.bundle.personal_connections.get(runtime_case.query.key) == connection
    assert await read_available(runtime_case.bundle, runtime_case.query) == previous
