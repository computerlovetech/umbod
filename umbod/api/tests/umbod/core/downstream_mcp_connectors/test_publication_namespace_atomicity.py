import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.umbod.core.downstream_mcp_connectors.test_unit_of_work_contract import (
    AggregateHarness,
    Harness,
    _inmemory,
    _published_prefix_command,
    _sqlite,
)
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError, PublicToolNameValidator
from umbod.core.connectors.downstream_mcp.errors import DownstreamConnectorNotFoundError, DownstreamConnectorUnavailableError
from umbod.core.connectors.downstream_mcp.management import (
    ApplyDiscoveredCatalog,
    DownstreamConnectorQueries,
    KeepCredential,
    KeepHealth,
    PreserveActivation,
    PreservePublication,
    PublishDownstreamConnectorAggregate,
    ReplaceCatalog,
    ReplaceDownstreamConnectorAggregate,
    UpdatePublishedConnectorPrefix,
)
from umbod.core.connectors.downstream_mcp.models import ConnectorHealthy, OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolPolicyInvalid, ReplacePersonalToolPolicy
from umbod.core.connectors.downstream_mcp.publishing.service import DownstreamConnectorPublisher
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition, ToolCatalogFound, create_downstream_mcp_stores


async def _database_inmemory(path: Path, fault: Callable[[str], None]) -> AggregateHarness:
    runtime = await prepared_inmemory_runtime()
    from umbod.core.messaging.stores.event_stream import DatabaseEventStream

    stores = await create_downstream_mcp_stores("namespace-secret", runtime.database)
    return Harness(stores.unit_of_work, stores.definitions, stores.credentials, stores.catalogs, stores.health, stores.publishing, stores.activations, stores.personal_connections, DatabaseEventStream(runtime.database))


@pytest_asyncio.fixture(params=(_inmemory, _database_inmemory, _sqlite), ids=("detached", "inmemory", "sqlite"))
async def aggregate(request: pytest.FixtureRequest, tmp_path: Path) -> AggregateHarness:
    factory: Callable[[Path, Callable[[str], None]], Awaitable[AggregateHarness]] = request.param
    path = tmp_path / "namespace.sqlite3"
    await prepared_sqlite_runtime(path)
    return await factory(path, lambda phase: None)


def _publish(connector_id: str, native: tuple[PublicToolIdentity, ...]) -> PublishDownstreamConnectorAggregate:
    return PublishDownstreamConnectorAggregate(connector_id=connector_id, native_identities=native)


@pytest.mark.asyncio
async def test_concurrent_publications_commit_one_normalized_namespace_claim(aggregate: AggregateHarness) -> None:
    await aggregate.unit_of_work.create(_published_prefix_command("alpha", "Shared-Name"))
    await aggregate.unit_of_work.create(_published_prefix_command("beta", "Shared_Name"))
    results = await asyncio.gather(
        aggregate.unit_of_work.publish(_publish("alpha", ())),
        aggregate.unit_of_work.publish(_publish("beta", ())),
        return_exceptions=True,
    )
    assert sum(result is True for result in results) == 1
    assert sum(isinstance(result, PublicToolNameConflictError) for result in results) == 1
    for connector_id, result in zip(("alpha", "beta"), results, strict=True):
        assert await aggregate.publishing.is_published(connector_id) is (result is True)


@pytest.mark.asyncio
async def test_native_identity_collision_prevents_publication(aggregate: AggregateHarness) -> None:
    await aggregate.unit_of_work.create(_published_prefix_command("alpha", "Native-Name"))
    native = (PublicToolIdentity(connector_id="native", tool_name_prefix="Native_Name", operation_name="search"),)
    with pytest.raises(PublicToolNameConflictError):
        await aggregate.unit_of_work.publish(_publish("alpha", native))
    assert not await aggregate.publishing.is_published("alpha")


@pytest.mark.asyncio
async def test_concurrent_publication_and_prefix_change_commit_only_one_claim(aggregate: AggregateHarness) -> None:
    alpha = _published_prefix_command("alpha", "Alpha")
    await aggregate.unit_of_work.create(alpha)
    await aggregate.unit_of_work.create(_published_prefix_command("beta", "Shared"))
    await aggregate.unit_of_work.publish(_publish("alpha", ()))
    results = await asyncio.gather(
        aggregate.unit_of_work.publish(_publish("beta", ())),
        aggregate.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(
            definition=alpha.definition.model_copy(update={"tool_name_prefix": "Shared"}), native_identities=(),
        )),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PublicToolNameConflictError) for result in results) == 1
    stored = await aggregate.definitions.get(ConnectorIdQuery(connector_id="alpha"))
    assert (stored.definition.tool_name_prefix == "Shared") is not await aggregate.publishing.is_published("beta")


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("discovery", "replacement"))
@pytest.mark.parametrize("collision", ("published", "native"))
async def test_published_catalogue_collision_rolls_back_catalogue_activation_and_publication(
    aggregate: AggregateHarness, mutation: str, collision: str,
) -> None:
    alpha = _published_prefix_command("alpha", "Shared")
    old_tool = alpha.catalog.snapshot.tools[0].model_copy(update={"identity": alpha.catalog.snapshot.tools[0].identity.model_copy(update={"downstream_name": "old"})})
    alpha = alpha.model_copy(update={"catalog": ReplaceCatalog(snapshot=alpha.catalog.snapshot.model_copy(update={"tools": (old_tool,)}))})
    await aggregate.unit_of_work.create(alpha)
    await aggregate.unit_of_work.publish(_publish("alpha", ()))
    native: tuple[PublicToolIdentity, ...] = ()
    if collision == "published":
        await aggregate.unit_of_work.create(_published_prefix_command("beta", "Shared"))
        await aggregate.unit_of_work.publish(_publish("beta", ()))
    else:
        native = (PublicToolIdentity(connector_id="native", tool_name_prefix="Shared", operation_name="search"),)
    capability = CapabilityRef(connector_kind="downstream_mcp", connector_id="alpha", capability_kind="tool", capability_key="old")
    await aggregate.activations.set_status(capability, ActivationStatus.ENABLED)
    snapshot = _published_prefix_command("alpha", "Shared").catalog.snapshot
    with pytest.raises(PublicToolNameConflictError):
        if mutation == "discovery":
            await aggregate.unit_of_work.apply_discovery(ApplyDiscoveredCatalog(
                admission=await aggregate.unit_of_work.admit_discovery("alpha"),
                connector_id="alpha", native_identities=native, catalog=snapshot,
                health=ConnectorHealthy(connector_id="alpha", checked_at=snapshot.discovered_at),
                operation_names=("search",),
            ))
        else:
            await aggregate.unit_of_work.replace(ReplaceDownstreamConnectorAggregate(
                native_identities=native, definition=alpha.definition, credential=KeepCredential(),
                catalog=ReplaceCatalog(snapshot=snapshot), health=KeepHealth(),
                activation=PreserveActivation(), publication=PreservePublication(),
            ))
    catalog = await aggregate.catalogs.get(ConnectorIdQuery(connector_id="alpha"))
    assert isinstance(catalog, ToolCatalogFound)
    assert catalog.snapshot == alpha.catalog.snapshot
    assert await aggregate.activations.get_status(capability) == ActivationStatus.ENABLED
    assert await aggregate.publishing.is_published("alpha")


@pytest.mark.asyncio
async def test_shared_publication_requires_nonempty_catalogue_and_missing_definition_fails(aggregate: AggregateHarness) -> None:
    command = _published_prefix_command("alpha", "Alpha")
    empty = command.model_copy(update={"catalog": ReplaceCatalog(snapshot=command.catalog.snapshot.model_copy(update={"tools": ()}))})
    await aggregate.unit_of_work.create(empty)
    with pytest.raises(DownstreamConnectorUnavailableError):
        await aggregate.unit_of_work.publish(_publish("alpha", ()))
    with pytest.raises(DownstreamConnectorNotFoundError):
        await aggregate.unit_of_work.publish(_publish("missing", ()))
    assert not await aggregate.publishing.is_published("alpha")


@pytest.mark.asyncio
async def test_personal_publication_does_not_require_catalogue(aggregate: AggregateHarness) -> None:
    await aggregate.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="personal", display_name="Personal", endpoint_url="https://personal.test/mcp", authorization_mode="personal",
    )))
    assert await aggregate.unit_of_work.publish(_publish("personal", ()))
    assert not await aggregate.unit_of_work.publish(_publish("personal", ()))
    assert await aggregate.publishing.is_published("personal")


class NativeIdentities:
    async def identities(self) -> tuple[PublicToolIdentity, ...]:
        return ()


@pytest.mark.asyncio
async def test_repeated_and_concurrent_publication_emits_only_one_event(aggregate: AggregateHarness) -> None:
    await aggregate.unit_of_work.create(_published_prefix_command("alpha", "Alpha"))
    queries = DownstreamConnectorQueries(aggregate.definitions, aggregate.credentials, aggregate.catalogs, aggregate.health, aggregate.publishing)
    publisher = DownstreamConnectorPublisher(aggregate.publishing, queries, aggregate.unit_of_work, NativeIdentities())
    await asyncio.gather(publisher.publish("alpha"), publisher.publish("alpha"))
    await publisher.publish("alpha")
    persisted = await aggregate.events.list_after(0, 100)
    assert len([entry for entry in persisted if entry.event.event_type == "connector.publication.changed"]) == 1


@pytest.mark.parametrize("adapter", ("inmemory", "sqlite"))
@pytest.mark.asyncio
async def test_personal_policy_publication_and_prefix_race_preserves_unique_published_namespace(tmp_path: Path, adapter: str) -> None:
    runtime = await prepared_inmemory_runtime() if adapter == "inmemory" else await prepared_sqlite_runtime(tmp_path / "race.sqlite3")
    bundle = await create_downstream_mcp_stores("namespace-secret", runtime.database)
    personal = OAuthConnectorDefinition(connector_id="personal", display_name="Personal", tool_name_prefix="Shared", endpoint_url="https://personal.test/mcp", authorization_mode="personal")
    await bundle.definitions.save(SaveConnectorDefinition(definition=personal))
    initial = _published_prefix_command("personal", "Shared").catalog.snapshot.tools[0]
    old_tool = initial.model_copy(update={"identity": initial.identity.model_copy(update={"downstream_name": "old"})})
    policy = (await bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(old_tool,), native_identities=()))).policy
    alpha = _published_prefix_command("alpha", "Alpha")
    await bundle.unit_of_work.create(alpha)
    await bundle.unit_of_work.create(_published_prefix_command("beta", "Shared"))
    await bundle.unit_of_work.publish(_publish("personal", ()))
    await bundle.unit_of_work.publish(_publish("alpha", ()))
    results = await asyncio.gather(
        bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=(initial,), native_identities=())),
        bundle.unit_of_work.publish(_publish("beta", ())),
        bundle.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(definition=alpha.definition.model_copy(update={"tool_name_prefix": "Shared"}), native_identities=())),
        return_exceptions=True,
    )
    assert isinstance(results[0], PersonalToolPolicyInvalid)
    assert sum(isinstance(result, PublicToolNameConflictError) for result in results[1:]) == 1
    assert await bundle.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal")) == policy
    identities: list[PublicToolIdentity] = []
    for definition in (await bundle.definitions.list()).definitions:
        if await bundle.publishing.is_published(definition.connector_id):
            catalog = await bundle.catalogs.get(ConnectorIdQuery(connector_id=definition.connector_id))
            assert isinstance(catalog, ToolCatalogFound)
            identities.extend(PublicToolIdentity(connector_id=definition.connector_id, tool_name_prefix=definition.tool_name_prefix, operation_name=tool.identity.downstream_name) for tool in catalog.snapshot.tools)
    PublicToolNameValidator().validate_unique(tuple(identities))


@pytest.mark.parametrize("adapter", ("inmemory", "sqlite"))
@pytest.mark.parametrize("policy_first", (True, False))
@pytest.mark.asyncio
async def test_personal_tool_replacement_and_published_prefix_change_serialize_namespace_claims(tmp_path: Path, adapter: str, policy_first: bool) -> None:
    runtime = await prepared_inmemory_runtime() if adapter == "inmemory" else await prepared_sqlite_runtime(tmp_path / "policy-prefix.sqlite3")
    bundle = await create_downstream_mcp_stores("namespace-secret", runtime.database)
    personal = OAuthConnectorDefinition(connector_id="personal", display_name="Personal", tool_name_prefix="Shared", endpoint_url="https://personal.test/mcp", authorization_mode="personal")
    await bundle.definitions.save(SaveConnectorDefinition(definition=personal))
    tool = _published_prefix_command("personal", "Shared").catalog.snapshot.tools[0]
    old_tool = tool.model_copy(update={"identity": tool.identity.model_copy(update={"downstream_name": "old"})})
    previous = (await bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(old_tool,), native_identities=()))).policy
    alpha = _published_prefix_command("alpha", "Alpha")
    await bundle.unit_of_work.create(alpha)
    await bundle.unit_of_work.publish(_publish("personal", ()))
    await bundle.unit_of_work.publish(_publish("alpha", ()))
    replacement = bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=previous.revision, tools=(tool,), native_identities=()))
    prefix = bundle.unit_of_work.update_published_prefix(UpdatePublishedConnectorPrefix(definition=alpha.definition.model_copy(update={"tool_name_prefix": "Shared"}), native_identities=()))
    operations = (replacement, prefix) if policy_first else (prefix, replacement)
    results = await asyncio.gather(*operations, return_exceptions=True)
    assert sum(isinstance(result, (PersonalToolPolicyInvalid, PublicToolNameConflictError)) for result in results) == 1
    current = await bundle.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal"))
    definition = await bundle.definitions.get(ConnectorIdQuery(connector_id="alpha"))
    assert (current.tools == (tool,)) is (definition.definition.tool_name_prefix == "Alpha")
    assert await bundle.publishing.is_published("personal")
    assert await bundle.publishing.is_published("alpha")


@pytest.mark.parametrize("adapter", ("inmemory", "sqlite"))
@pytest.mark.asyncio
async def test_unchanged_personal_policy_with_intact_projection_ignores_colliding_drafts(tmp_path: Path, adapter: str) -> None:
    runtime = await prepared_inmemory_runtime() if adapter == "inmemory" else await prepared_sqlite_runtime(tmp_path / "noop.sqlite3")
    bundle = await create_downstream_mcp_stores("namespace-secret", runtime.database)
    await bundle.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(connector_id="personal", display_name="Personal", endpoint_url="https://personal.test/mcp", authorization_mode="personal")))
    tool = _published_prefix_command("personal", "Personal").catalog.snapshot.tools[0]
    policy = (await bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(tool,), native_identities=()))).policy
    for connector_id in ("alpha", "beta"):
        await bundle.unit_of_work.create(_published_prefix_command(connector_id, "Draft"))
    result = await bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=(tool,), native_identities=()))
    assert result.policy == policy
    assert result.changed_tools == result.revoked_grants == ()
