from datetime import timedelta

import pytest

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.personal_oauth_applications import application_clock, application_credentials, install_application_policy
from tests.support.personal_oauth_cases import ControlledClock
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_application_schema import PERSONAL_OAUTH_APPLICATION_TABLE
from umbod.core.connectors.downstream_mcp.stores.queries import query_all
from umbod.core.persistence import NoFilter
from umbod.core.connectors.downstream_mcp.personal.oauth.applications.models import (
    ClaimedOAuthApplication, CompleteOAuthApplication, ExpiringApplicationSecret,
    OAuthApplicationUnavailable, RegisteredApplicationReference, ResolveOAuthApplication,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.configuration import PersonalOAuthSettings, DynamicConfidentialOAuthClient, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_applications import EncryptedPersonalOAuthApplicationStore


@pytest.mark.asyncio
async def test_expiry_preserves_old_reference_and_allocates_new_registration() -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        binding = await install_application_policy(runtime.database)
        clock = ControlledClock(application_clock())
        store = EncryptedPersonalOAuthApplicationStore(runtime.database, AuthenticatedTextCipher("test-secret"), clock)
        claim = await store.reserve(binding)
        assert isinstance(claim, ClaimedOAuthApplication)
        credentials = application_credentials().model_copy(update={"lifetime": ExpiringApplicationSecret(expires_at=clock.now + timedelta(minutes=1))})
        first = await store.complete(CompleteOAuthApplication(claim=claim, credentials=credentials))
        assert await store.reserve(binding) == first
        clock.now += timedelta(minutes=2)
        replacement = await store.reserve(binding)
        assert isinstance(replacement, ClaimedOAuthApplication)
        assert replacement.registration_id != first.registration_id
        await store.complete(CompleteOAuthApplication(claim=replacement, credentials=application_credentials()))
        with pytest.raises(OAuthApplicationUnavailable):
            await store.resolve(ResolveOAuthApplication(reference=RegisteredApplicationReference(registration_id=first.registration_id), binding=binding, client_id=first.credentials.client_id))
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_pending_claim_blocks_replay_but_not_independent_callback_binding() -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        binding = await install_application_policy(runtime.database)
        store = EncryptedPersonalOAuthApplicationStore(runtime.database, AuthenticatedTextCipher("test-secret"), application_clock)
        first = await store.reserve(binding)
        with pytest.raises(OAuthApplicationUnavailable):
            await store.reserve(binding)
        independent = await store.reserve(binding.model_copy(update={"redirect_uri": "https://umbod.example/other-callback"}))
        assert independent.registration_id != first.registration_id
        with pytest.raises(OAuthApplicationUnavailable):
            await store.complete(CompleteOAuthApplication(claim=first.model_copy(update={"claim_id": "forged-owner"}), credentials=application_credentials()))
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["replace", "delete"])
async def test_policy_mutation_cleans_secrets_and_fences_late_completion(mutation: str) -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        binding = await install_application_policy(runtime.database)
        stores = await create_downstream_mcp_stores("test-secret", runtime.database)
        store = stores.personal_oauth_applications
        ready_claim = await store.reserve(binding)
        assert isinstance(ready_claim, ClaimedOAuthApplication)
        ready = await store.complete(CompleteOAuthApplication(claim=ready_claim, credentials=application_credentials()))
        pending = await store.reserve(binding.model_copy(update={"redirect_uri": "https://umbod.example/other"}))
        assert isinstance(pending, ClaimedOAuthApplication)
        if mutation == "replace":
            await stores.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
                connector_id=binding.connector_id, expected_revision=binding.configuration_revision,
                settings=PersonalOAuthSettings(requested_scopes=(), client=DynamicConfidentialOAuthClient(token_endpoint_auth_method="client_secret_basic")),
            ))
        else:
            await stores.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id=binding.connector_id))
        async with runtime.database.read_session() as session:
            assert not await session.find_many(PERSONAL_OAUTH_APPLICATION_TABLE, query_all(NoFilter()))
        with pytest.raises(ValueError):
            await store.complete(CompleteOAuthApplication(claim=pending, credentials=application_credentials()))
        with pytest.raises(ValueError):
            await store.resolve(ResolveOAuthApplication(reference=RegisteredApplicationReference(registration_id=ready.registration_id), binding=binding, client_id=ready.credentials.client_id))
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_missing_root_secret_disables_application_registration() -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        binding = await install_application_policy(runtime.database)
        stores = await create_downstream_mcp_stores("", runtime.database)
        with pytest.raises(OAuthApplicationUnavailable):
            await stores.personal_oauth_applications.reserve(binding)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_arbitrary_resource_cannot_reserve_under_existing_connector() -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        binding = await install_application_policy(runtime.database)
        store = EncryptedPersonalOAuthApplicationStore(runtime.database, AuthenticatedTextCipher("test-secret"), application_clock)
        with pytest.raises(OAuthApplicationUnavailable):
            await store.reserve(binding.model_copy(update={"resource": "https://unrelated.example/mcp"}))
    finally:
        await runtime.shutdown()
