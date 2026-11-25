import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.personal_oauth_diagnostics import RecordingOAuthFailureObserver
from tests.support.personal_oauth_setup import SETUP_CALLBACK, SuccessfulSetupProvider, install_setup_validation
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.management import PublishDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal.oauth.failures import OAuthFailureEvidence
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization.models import PersonalOAuthProviderFailure
from umbod.core.connectors.downstream_mcp.personal.oauth.configuration import DynamicPublicOAuthClient, PersonalOAuthConfigurationQuery, PersonalOAuthSettings, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.personal.oauth.setup.models import PersonalOAuthSetupScopeMismatch, PersonalOAuthSetupValidation, ValidatePersonalOAuthSetup
from umbod.core.connectors.downstream_mcp.personal.oauth.setup.service import PersonalOAuthSetupService
from umbod.core.connectors.downstream_mcp.personal.oauth.setup.state import CompletePersonalOAuthSetup, PersonalOAuthSetupConflict, PersonalOAuthSetupQuery, PersonalOAuthSetupRequired, SetupFailed, SetupInProgress, SetupRequired, SetupValidated, StartPersonalOAuthSetup
from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores, SaveConnectorDefinition, create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_setup import PersonalOAuthSetupStoreService
from umbod.core.invocation.diagnostics import DownstreamHttpResponse


@dataclass
class ControlledClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class SetupCase:
    stores: DownstreamMcpStores
    store: PersonalOAuthSetupStoreService
    clock: ControlledClock
    failures: RecordingOAuthFailureObserver

    @property
    def query(self) -> PersonalOAuthSetupQuery:
        return PersonalOAuthSetupQuery(connector_id="personal", redirect_uri=SETUP_CALLBACK)

    def service(self, provider: SuccessfulSetupProvider) -> PersonalOAuthSetupService:
        return PersonalOAuthSetupService(self.store, provider, self.failures, self.clock)

    async def command(self, operation: str = "validation") -> StartPersonalOAuthSetup:
        status = await self.store.get(self.query)
        return StartPersonalOAuthSetup(**self.query.model_dump(), operation=operation, expected_revision=status.revision)


@pytest_asyncio.fixture
async def case() -> AsyncIterator[SetupCase]:
    runtime = await prepared_inmemory_runtime()
    try:
        stores = await create_downstream_mcp_stores("setup-test-secret", runtime.database)
        await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(connector_id="personal", display_name="Personal", endpoint_url="https://tools.example/mcp", authorization_mode="personal")))
        clock = ControlledClock(datetime(2026, 6, 1, tzinfo=UTC))
        yield SetupCase(stores, PersonalOAuthSetupStoreService(runtime.database, AuthenticatedTextCipher("setup-test-secret"), clock), clock, RecordingOAuthFailureObserver())
    finally:
        await runtime.shutdown()


def publication(callback: str = SETUP_CALLBACK) -> PublishDownstreamConnectorAggregate:
    return PublishDownstreamConnectorAggregate(connector_id="personal", native_identities=(), personal_oauth_redirect_uri=callback)


@pytest.mark.asyncio
async def test_new_connector_requires_validation_at_atomic_publication_boundary(case: SetupCase) -> None:
    assert isinstance((await case.store.get(case.query)).state, SetupRequired)
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())
    assert not await case.stores.publishing.is_published("personal")


@pytest.mark.asyncio
async def test_validation_records_checked_time_and_allows_publication_without_catalogue(case: SetupCase) -> None:
    result = await case.service(SuccessfulSetupProvider()).run(await case.command())
    assert isinstance(result.state, SetupValidated)
    assert result.state.checked_at == case.clock.now
    assert await case.stores.unit_of_work.publish(publication())
    assert case.failures.failures == []


@pytest.mark.asyncio
async def test_discovery_is_not_a_successful_validation_receipt(case: SetupCase) -> None:
    status = await case.service(SuccessfulSetupProvider()).run(await case.command("discovery"))
    assert status.state.status == "discovered"
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())


@pytest.mark.asyncio
async def test_validation_start_immediately_revokes_previous_success(case: SetupCase) -> None:
    await case.service(SuccessfulSetupProvider()).run(await case.command())
    await case.store.start(await case.command())
    assert isinstance((await case.store.get(case.query)).state, SetupInProgress)
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())


@pytest.mark.asyncio
async def test_current_receipt_does_not_authorize_another_configured_callback(case: SetupCase) -> None:
    await case.service(SuccessfulSetupProvider()).run(await case.command())
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication("https://changed.example/callback"))


@pytest.mark.asyncio
async def test_definition_changes_make_successful_receipt_stale(case: SetupCase) -> None:
    await case.service(SuccessfulSetupProvider()).run(await case.command())
    await case.stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(connector_id="personal", display_name="Personal", endpoint_url="https://changed.example/mcp", authorization_mode="personal")))
    assert isinstance((await case.store.get(case.query)).state, SetupRequired)
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())


@pytest.mark.asyncio
async def test_policy_change_invalidates_receipt_and_unpublishes_atomically(case: SetupCase) -> None:
    await install_setup_validation(case.stores, "personal")
    await case.stores.unit_of_work.publish(publication())
    await case.stores.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision="legacy", settings=PersonalOAuthSettings(requested_scopes=("read",), client=DynamicPublicOAuthClient())))
    assert not await case.stores.publishing.is_published("personal")
    assert isinstance((await case.store.get(case.query)).state, SetupRequired)
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())


@pytest.mark.asyncio
async def test_unchanged_policy_preserves_current_validation(case: SetupCase) -> None:
    await case.service(SuccessfulSetupProvider()).run(await case.command())
    configuration = await case.stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
    await case.stores.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=(), client=configuration.policy.client)))
    assert await case.stores.unit_of_work.publish(publication())


@pytest.mark.asyncio
async def test_stale_revision_cannot_start_or_invalidate_validation(case: SetupCase) -> None:
    old = await case.command()
    await case.service(SuccessfulSetupProvider()).run(old)
    with pytest.raises(PersonalOAuthSetupConflict):
        await case.store.start(old)
    assert await case.stores.unit_of_work.publish(publication())


@pytest.mark.asyncio
async def test_unexpired_operation_blocks_duplicate_remote_side_effect(case: SetupCase) -> None:
    command = await case.command()
    await case.store.start(command)
    with pytest.raises(PersonalOAuthSetupConflict):
        await case.service(SuccessfulSetupProvider()).run(await case.command())


@pytest.mark.asyncio
async def test_expired_lease_recovers_but_late_success_cannot_win(case: SetupCase) -> None:
    started = await case.store.start(await case.command())
    result = await SuccessfulSetupProvider().validate(ValidatePersonalOAuthSetup(endpoint_url=started.endpoint_url, redirect_uri=SETUP_CALLBACK, policy=started.policy))
    case.clock.now += timedelta(seconds=90)
    assert isinstance((await case.store.get(case.query)).state, SetupRequired)
    latest = await case.service(SuccessfulSetupProvider()).run(await case.command())
    with pytest.raises(PersonalOAuthSetupConflict):
        await case.store.complete(CompletePersonalOAuthSetup(started=started, state=SetupValidated(result=result, checked_at=case.clock.now)))
    assert await case.store.get(case.query) == latest


class FailingSetupProvider(SuccessfulSetupProvider):
    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation:
        raise PersonalOAuthProviderFailure(OAuthFailureEvidence(stage="registration", reason="provider_rejected", downstream_response=DownstreamHttpResponse(status_code=400)))


@pytest.mark.asyncio
async def test_failure_is_durable_sanitized_and_observed_once_without_retry(case: SetupCase) -> None:
    result = await case.service(FailingSetupProvider()).run(await case.command())
    assert isinstance(result.state, SetupFailed)
    assert result.state.stage == "registration"
    assert result.state.reason == "provider_rejected"
    assert result == await case.store.get(case.query)
    assert len(case.failures.failures) == 1
    assert case.failures.failures[0][1].downstream_response == DownstreamHttpResponse(status_code=400)


class MismatchedSetupProvider(SuccessfulSetupProvider):
    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation:
        return PersonalOAuthSetupScopeMismatch(discovery=await self.discover(command), returned_scopes=("candidate.read",), downstream_response=DownstreamHttpResponse(status_code=201))


@pytest.mark.asyncio
async def test_scope_mismatch_returns_candidate_but_never_approves_it_or_publishes(case: SetupCase) -> None:
    status = await case.service(MismatchedSetupProvider()).run(await case.command())
    assert status.state.status == "scope_mismatch"
    configuration = await case.stores.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
    assert configuration.policy.requested_scopes == ()
    assert case.failures.failures == [("personal", OAuthFailureEvidence(stage="registration", reason="scope_mismatch", downstream_response=DownstreamHttpResponse(status_code=201)))]
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())


class PausingSetupProvider(SuccessfulSetupProvider):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation:
        self.started.set()
        await self.release.wait()
        return await super().validate(command)


@pytest.mark.asyncio
async def test_policy_change_during_network_operation_makes_result_stale(case: SetupCase) -> None:
    provider = PausingSetupProvider()
    task = asyncio.create_task(case.service(provider).run(await case.command()))
    try:
        await asyncio.wait_for(provider.started.wait(), timeout=2)
        await asyncio.wait_for(case.stores.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision="legacy", settings=PersonalOAuthSettings(requested_scopes=("read",), client=DynamicPublicOAuthClient()))), timeout=2)
    finally:
        provider.release.set()
    with pytest.raises(PersonalOAuthSetupConflict):
        await task
    assert isinstance((await case.store.get(case.query)).state, SetupRequired)


@pytest.mark.asyncio
async def test_existing_publication_is_not_bulk_revoked_without_policy_change(case: SetupCase) -> None:
    await case.stores.publishing.publish_connector("personal")
    with pytest.raises(PersonalOAuthSetupRequired):
        await case.stores.unit_of_work.publish(publication())
    assert await case.stores.publishing.is_published("personal")
