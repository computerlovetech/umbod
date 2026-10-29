from messaging.ports import EventStream
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from dataclasses import replace
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey, PersonalConnectionStore, SetPersonalConnectionEnabled, InMemoryPersonalConnectionStore
from umbod.core.connectors.downstream_mcp.stores.personal_connections import EncryptedPersonalConnectionStore
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.activation import ActivationStatus, ActivationStore, CapabilityRef
from umbod.core.connectors.downstream_mcp.management.unit_of_work import ApplyDiscoveredCatalog, DeleteCatalog, InvalidateDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.models import ConnectorUnhealthy
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.core.activation import CAPABILITY_ACTIVATION_STATE_TABLE, create_capability_activation_store
from umbod.core.activation.stores.service import CapabilityActivationStoreService
from umbod.core.connectors.downstream_mcp.management import DownstreamConnectorUnitOfWorkService, InMemoryDownstreamConnectorUnitOfWork, utc_clock
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, CONNECTOR_HEALTH_TABLE, ConnectorDefinitionStoreService, ConnectorHealthStoreService, EncryptedCredentialStoreService, TOOL_CATALOG_TABLE, ToolCatalogStoreService
from tests.persistence_runtime import create_inmemory_runtime, create_sqlite_runtime, prepared_sqlite_runtime
import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
import pytest
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.capabilities.tools.names import PublicToolNameConflictError
from umbod.core.connectors.downstream_mcp.models import ConnectorHealthy, DiscoveredToolWithoutOutputSchema, StaticBearerConnectorDefinition, StaticBearerCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore, ConnectorHealthStore, ConnectorIdQuery, CredentialFound, EncryptedCredentialStore, ToolCatalogFound, ToolCatalogStore
from umbod.core.connectors.downstream_mcp.management import CreateDownstreamConnectorAggregate, DownstreamConnectorUnitOfWork, PreservePublication, ReconcileActivation, ReplaceCatalog, ReplaceCredential, ReplaceHealth, UpdatePublishedConnectorPrefix

class AggregateHarness(Protocol):
    unit_of_work: DownstreamConnectorUnitOfWork
    events: EventStream
    personal_connections: PersonalConnectionStore
    definitions: ConnectorDefinitionStore
    credentials: EncryptedCredentialStore
    catalogs: ToolCatalogStore
    health: ConnectorHealthStore
    publishing: ConnectorPublishingStore
    activations: ActivationStore

class Harness:

    def __init__(self, unit_of_work: DownstreamConnectorUnitOfWork, definitions: ConnectorDefinitionStore, credentials: EncryptedCredentialStore, catalogs: ToolCatalogStore, health: ConnectorHealthStore, publishing: ConnectorPublishingStore, activations: ActivationStore, personal_connections: PersonalConnectionStore, events: EventStream) -> None:
        self.events = events
        self.unit_of_work = unit_of_work
        self.personal_connections = personal_connections
        self.definitions = definitions
        self.credentials = credentials
        self.catalogs = catalogs
        self.health = health
        self.publishing = publishing
        self.activations = activations

def _command() -> CreateDownstreamConnectorAggregate:
    checked_at = datetime(2026, 1, 2, tzinfo=UTC)
    return CreateDownstreamConnectorAggregate(definition=StaticBearerConnectorDefinition(connector_id='alpha', display_name='Alpha', capability_description='Manage downstream tools', endpoint_url='https://example.test/mcp'), credential=ReplaceCredential(credential=StaticBearerCredentialState(connector_id='alpha', bearer_token='secret-token')), catalog=ReplaceCatalog(snapshot=ToolCatalogSnapshot(connector_id='alpha', discovered_at=checked_at, tools=())), health=ReplaceHealth(health=ConnectorHealthy(connector_id='alpha', checked_at=checked_at)), activation=ReconcileActivation(operation_names=()), publication=PreservePublication())

async def _inmemory(_: Path, fault: Callable[[str], None]) -> AggregateHarness:
    from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import EncryptedPersonalOAuthConfigurationStore

    from umbod.core.connectors.downstream_mcp.stores.personal_tool_policies import PersonalToolPolicyStoreService
    from umbod.core.connectors.downstream_mcp.stores.personal_tool_access import EncryptedPersonalToolAccessStore

    definition_database = create_inmemory_runtime().database
    personal_policies = PersonalToolPolicyStoreService(definition_database, utc_clock, fault)
    personal_access = EncryptedPersonalToolAccessStore(definition_database, AuthenticatedTextCipher('unit-of-work-secret'))
    definitions = ConnectorDefinitionStoreService(definition_database, CONNECTOR_DEFINITION_TABLE)
    configurations = EncryptedPersonalOAuthConfigurationStore(definition_database, AuthenticatedTextCipher('unit-of-work-secret'))
    credentials = EncryptedCredentialStoreService(create_inmemory_runtime().database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('unit-of-work-secret'))
    catalogs = ToolCatalogStoreService(create_inmemory_runtime().database, TOOL_CATALOG_TABLE)
    health = ConnectorHealthStoreService(create_inmemory_runtime().database, CONNECTOR_HEALTH_TABLE)
    database = create_inmemory_runtime().database
    activations = CapabilityActivationStoreService(database, CAPABILITY_ACTIVATION_STATE_TABLE)
    publishing = ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
    personal = InMemoryPersonalConnectionStore()
    events = DatabaseEventStream(create_inmemory_runtime().database)
    return Harness(InMemoryDownstreamConnectorUnitOfWork(definitions, credentials, catalogs, health, activations, publishing, fault, personal, configurations, personal_policies, personal_access, events), definitions, credentials, catalogs, health, publishing, activations, personal, events)

async def _sqlite(path: Path, fault: Callable[[str], None]) -> AggregateHarness:
    definitions = ConnectorDefinitionStoreService(create_sqlite_runtime(path).database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(create_sqlite_runtime(path).database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher('unit-of-work-secret'))
    catalogs = ToolCatalogStoreService(create_sqlite_runtime(path).database, TOOL_CATALOG_TABLE)
    health = ConnectorHealthStoreService(create_sqlite_runtime(path).database, CONNECTOR_HEALTH_TABLE)
    database = (await prepared_sqlite_runtime(path)).database
    activations = await create_capability_activation_store(database)
    publishing = await create_connector_publishing_store(database)
    return Harness(DownstreamConnectorUnitOfWorkService(create_sqlite_runtime(path).database, AuthenticatedTextCipher('unit-of-work-secret'), fault, utc_clock), definitions, credentials, catalogs, health, publishing, activations, EncryptedPersonalConnectionStore(database, AuthenticatedTextCipher('unit-of-work-secret')), DatabaseEventStream(database))

@pytest.mark.parametrize('factory', (_inmemory, _sqlite), ids=('inmemory', 'sqlite'))
@pytest.mark.asyncio
async def test_atomic_create_persists_complete_aggregate(tmp_path: Path, factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]]) -> None:
    database_path = tmp_path / 'aggregate.sqlite3'
    harness = await factory(database_path, lambda phase: None)
    await harness.unit_of_work.create(_command())
    query = ConnectorIdQuery(connector_id='alpha')
    assert (await harness.definitions.get(query)).found is True
    credential = await harness.credentials.get(query)
    assert isinstance(credential, CredentialFound)
    assert credential.credential.bearer_token.get_secret_value() == 'secret-token'
    assert isinstance(await harness.catalogs.get(query), ToolCatalogFound)
    assert (await harness.health.get(query)).found is True

@pytest.mark.parametrize('factory', (_inmemory, _sqlite), ids=('inmemory', 'sqlite'))
@pytest.mark.parametrize('failed_phase', ('definition', 'credential', 'catalog', 'health', 'activation', 'event'))
@pytest.mark.asyncio
async def test_create_failure_at_each_phase_rolls_back_all_state(tmp_path: Path, factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]], failed_phase: str) -> None:

    def fail(phase: str) -> None:
        if phase == failed_phase:
            raise RuntimeError(f'injected {phase} failure')
    database_path = tmp_path / f'{failed_phase}.sqlite3'
    harness = await factory(database_path, fail)
    with pytest.raises(RuntimeError, match=f'injected {failed_phase} failure'):
        await harness.unit_of_work.create(_command())
    query = ConnectorIdQuery(connector_id='alpha')
    assert (await harness.definitions.get(query)).found is False
    assert (await harness.credentials.get(query)).found is False
    assert (await harness.catalogs.get(query)).found is False
    assert (await harness.health.get(query)).found is False

@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.parametrize("failed_phase", ("none", "credential", "definition", "publication"))
@pytest.mark.asyncio
async def test_connector_deletion_personal_cleanup_is_atomic(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
    failed_phase: str,
) -> None:
    deleting = False

    def fault(phase: str) -> None:
        if deleting and phase == failed_phase:
            raise RuntimeError("delete failed")

    path = tmp_path / "delete.sqlite3"
    harness = await factory(path, fault)
    await harness.unit_of_work.create(_command())
    keys = tuple(PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject=owner), connector_id="alpha") for owner in ("one", "two"))
    before = tuple([await harness.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True)) for key in keys])
    deleting = True
    command = DeleteDownstreamConnectorAggregate(connector_id="alpha")
    if failed_phase == "none":
        await harness.unit_of_work.delete(command)
        for key in keys:
            assert not (await harness.personal_connections.get(key)).enabled
        assert not (await harness.definitions.get(ConnectorIdQuery(connector_id="alpha"))).found
    else:
        with pytest.raises(RuntimeError, match="delete failed"):
            await harness.unit_of_work.delete(command)
        assert tuple([await harness.personal_connections.get(key) for key in keys]) == before
        assert (await harness.definitions.get(ConnectorIdQuery(connector_id="alpha"))).found


def _published_prefix_command(connector_id: str, tool_name_prefix: str) -> CreateDownstreamConnectorAggregate:
    checked_at = datetime(2026, 1, 2, tzinfo=UTC)
    return CreateDownstreamConnectorAggregate(definition=StaticBearerConnectorDefinition(connector_id=connector_id, display_name=connector_id.title(), tool_name_prefix=tool_name_prefix, capability_description=f'Manage {connector_id} tools', endpoint_url=f'https://{connector_id}.test/mcp'), credential=ReplaceCredential(credential=StaticBearerCredentialState(connector_id=connector_id, bearer_token='secret-token')), catalog=ReplaceCatalog(snapshot=ToolCatalogSnapshot(connector_id=connector_id, discovered_at=checked_at, tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name='search'), title='Search', description='Search', input_schema={'type': 'object'}),))), health=ReplaceHealth(health=ConnectorHealthy(connector_id=connector_id, checked_at=checked_at)), activation=ReconcileActivation(operation_names=('search',)), publication=PreservePublication())

@pytest.mark.asyncio
async def test_sqlite_concurrent_prefix_updates_commit_only_one_conflicting_claim(tmp_path: Path) -> None:
    database_path = tmp_path / 'concurrent-prefix.sqlite3'
    first = await _sqlite(database_path, lambda phase: None)
    second = await _sqlite(database_path, lambda phase: None)
    alpha = _published_prefix_command('alpha', 'Alpha')
    beta = _published_prefix_command('beta', 'Beta')
    await first.unit_of_work.create(alpha)
    await first.unit_of_work.create(beta)
    await first.publishing.publish_connector('alpha')
    await first.publishing.publish_connector('beta')
    results = await asyncio.gather(first.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(definition=alpha.definition.model_copy(update={'tool_name_prefix': 'Shared'}), native_identities=())), second.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(definition=beta.definition.model_copy(update={'tool_name_prefix': 'Shared'}), native_identities=())), return_exceptions=True)
    assert sum((result is None for result in results)) == 1
    assert sum((isinstance(result, PublicToolNameConflictError) for result in results)) == 1
    stored_alpha = await first.definitions.get(ConnectorIdQuery(connector_id='alpha'))
    stored_beta = await first.definitions.get(ConnectorIdQuery(connector_id='beta'))
    assert {stored_alpha.definition.tool_name_prefix, stored_beta.definition.tool_name_prefix} in ({'Shared', 'Alpha'}, {'Shared', 'Beta'})


@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.parametrize("interruption", ("discovery_failure", "authorization_invalidation"))
@pytest.mark.asyncio
async def test_reconnect_preserves_tool_choices(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
    interruption: str,
) -> None:
    path = tmp_path / "reconnect.sqlite3"
    harness = await factory(path, lambda phase: None)
    command = _published_prefix_command("alpha", "Alpha")
    await harness.unit_of_work.create(command)
    await harness.publishing.publish_connector("alpha")
    enabled = CapabilityRef(connector_kind="downstream_mcp", connector_id="alpha", capability_kind="tool", capability_key="search")
    disabled = replace(enabled, capability_key="disabled")
    added = replace(enabled, capability_key="new")
    await harness.activations.set_status(enabled, ActivationStatus.ENABLED)
    await harness.activations.set_status(disabled, ActivationStatus.DISABLED)
    health = ConnectorUnhealthy(connector_id="alpha", checked_at=command.health.health.checked_at, reason="auth_rejected")
    for _ in range(2):
        if interruption == "discovery_failure":
            await harness.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
                admission=await harness.unit_of_work.admit_discovery("alpha"),
                native_identities=(), connector_id="alpha", catalog=DeleteCatalog(), health=health, operation_names=(),
            ))
        else:
            await harness.unit_of_work.invalidate(InvalidateDownstreamConnectorAggregate(connector_id="alpha", health=health))
            assert not await harness.publishing.is_published("alpha")
        assert not isinstance(await harness.catalogs.get(ConnectorIdQuery(connector_id="alpha")), ToolCatalogFound)
        assert await harness.activations.get_status(enabled) == ActivationStatus.ENABLED
        assert await harness.activations.get_status(disabled) == ActivationStatus.DISABLED

    snapshot = command.catalog.snapshot.model_copy(update={"tools": tuple(
        command.catalog.snapshot.tools[0].model_copy(update={"identity": ToolIdentity(connector_id="alpha", downstream_name=name)})
        for name in ("search", "disabled", "new")
    )})
    for _ in range(2):
        await harness.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
                admission=await harness.unit_of_work.admit_discovery("alpha"),
            native_identities=(), connector_id="alpha", catalog=snapshot, health=command.health.health,
            operation_names=("search", "disabled", "new"),
        ))
        assert await harness.activations.get_status(enabled) == ActivationStatus.ENABLED
        assert await harness.activations.get_status(disabled) == ActivationStatus.DISABLED
        assert await harness.activations.get_status(added) == ActivationStatus.DISABLED


@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.parametrize("personal", (False, True), ids=("shared", "personal"))
@pytest.mark.asyncio
async def test_unpublished_create_and_delete_publish_discovery_events(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
    personal: bool,
) -> None:
    path = tmp_path / "discovery-events.sqlite3"
    harness = await factory(path, lambda phase: None)
    command = _command()
    if personal:
        from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
        from umbod.core.connectors.downstream_mcp.management import DeleteCredential, DeleteHealth

        command = command.model_copy(update={
            "definition": OAuthConnectorDefinition(connector_id="alpha", display_name="Alpha", endpoint_url="https://example.test/mcp", authorization_mode="personal"),
            "credential": DeleteCredential(), "catalog": DeleteCatalog(), "health": DeleteHealth(),
        })
    await harness.unit_of_work.create(command)
    await harness.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="alpha"))
    events = await harness.events.list_after(0, 100)
    assert [entry.event.event_type for entry in events] == ["connector.discovery.changed"] * 2
    assert all(entry.event.metadata == {"connector_kind": "downstream_mcp", "connector_id": "alpha"} for entry in events)


@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.asyncio
async def test_delete_event_failure_restores_unpublished_definition(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
) -> None:
    deleting = False

    def fault(phase: str) -> None:
        if deleting and phase == "event":
            raise RuntimeError("event append failed")

    path = tmp_path / "delete-event-failure.sqlite3"
    harness = await factory(path, fault)
    await harness.unit_of_work.create(_command())
    deleting = True
    with pytest.raises(RuntimeError, match="event append failed"):
        await harness.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="alpha"))
    assert (await harness.definitions.get(ConnectorIdQuery(connector_id="alpha"))).found
    assert len(await harness.events.list_after(0, 100)) == 1


@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.asyncio
async def test_stale_discovery_does_not_restore_deleted_connector(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
) -> None:
    path = tmp_path / "stale-discovery.sqlite3"
    harness = await factory(path, lambda phase: None)
    command = _command()
    await harness.unit_of_work.create(command)
    admission = await harness.unit_of_work.admit_discovery("alpha")
    await harness.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="alpha"))
    from umbod.core.connectors.downstream_mcp.errors import DownstreamConnectorNotFoundError, DownstreamConnectorUnavailableError

    with pytest.raises((DownstreamConnectorNotFoundError, DownstreamConnectorUnavailableError)):
        await harness.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
            admission=admission,
            native_identities=(), connector_id="alpha", catalog=command.catalog.snapshot,
            health=command.health.health, operation_names=(),
        ))
    assert not (await harness.catalogs.get(ConnectorIdQuery(connector_id="alpha"))).found
    assert len(await harness.events.list_after(0, 100)) == 2


@pytest.mark.parametrize("factory", (_inmemory, _sqlite), ids=("inmemory", "sqlite"))
@pytest.mark.asyncio
async def test_catalog_generation_rejects_a_later_commit_even_when_content_is_identical(
    tmp_path: Path,
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]],
) -> None:
    from umbod.core.connectors.downstream_mcp.errors import ObsoleteDownstreamCatalogError

    path = tmp_path / "obsolete.sqlite3"
    harness = await factory(path, lambda phase: None)
    command = _command()
    await harness.unit_of_work.create(command)
    admission = await harness.unit_of_work.admit_discovery("alpha")
    newer = command.catalog.snapshot
    await harness.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
        admission=admission, native_identities=(), connector_id="alpha",
        catalog=newer, health=command.health.health, operation_names=(),
    ))
    with pytest.raises(ObsoleteDownstreamCatalogError):
        await harness.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
            admission=admission, native_identities=(), connector_id="alpha",
            catalog=command.catalog.snapshot, health=command.health.health, operation_names=(),
        ))
    persisted = await harness.catalogs.get(ConnectorIdQuery(connector_id="alpha"))
    assert isinstance(persisted, ToolCatalogFound)
    assert persisted.snapshot == newer
