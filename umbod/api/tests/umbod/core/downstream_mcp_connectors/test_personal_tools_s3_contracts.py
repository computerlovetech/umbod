from datetime import timedelta

import asyncio
from pathlib import Path

import pytest
from jsonschema import ValidationError
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.capabilities.domain import CapabilityIdentity
from umbod.core.connectors.downstream_mcp.management import DeleteDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.models import DiscoveredTool, DiscoveredToolWithoutOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_tools import (
    AdmitPersonalTool,
    PersonalToolDiscoveryService,
    PersonalToolMatch,
    PersonalToolPolicy,
    PersonalToolPolicyConflict,
    PersonalToolPolicyInvalid,
    ReplacePersonalToolPolicy,
    SavePersonalToolObservation,
    contract_fingerprint,
    validate_arguments,
    validate_contract_schema,
)
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.personal_tool_policies import PersonalToolPolicyStoreService
from umbod.core.permissions.stores.schema import CAPABILITY_PERMISSION_TABLE, CONNECTOR_PERMISSION_TABLE, GroupCapabilityPermissionKey, GroupCapabilityPermissionRecord
from umbod.core.persistence import AllFields, DeleteQuery, NoFilter, Query, TransactionMode, Unordered, UpsertCommand

__all__ = ["runtime_case"]


def approved_tool(name: str) -> DiscoveredTool:
    return DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id="personal", downstream_name=name), title="Administrator title", description="Administrator description", input_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False})


async def replace_policy(case: RuntimeCase, tools: tuple[DiscoveredTool, ...]) -> PersonalToolPolicy:
    previous = await case.bundle.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal"))
    result = await case.bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=previous.revision, tools=tools, native_identities=()))
    return result.policy


async def enable_tool(case: RuntimeCase, name: str) -> None:
    await case.bundle.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key=name), ActivationStatus.ENABLED)
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(CAPABILITY_PERMISSION_TABLE, UpsertCommand(key=GroupCapabilityPermissionKey(group_id="team", connector_id="personal", capability_kind="tool", capability_key=name), row=GroupCapabilityPermissionRecord(group_id="team", connector_id="personal", capability_kind="tool", capability_key=name)))


async def save_matches(case: RuntimeCase, policy: PersonalToolPolicy) -> SavePersonalToolObservation:
    target = await case.store.resolve(case.query)
    command = SavePersonalToolObservation(query=case.query, target=target, contract_revision=policy.revision, matches=tuple(PersonalToolMatch(name=tool.identity.downstream_name, fingerprint=contract_fingerprint(tool)) for tool in policy.tools), expires_at=target.expires_at)
    await case.bundle.personal_tool_access.save_observation(command)
    return command


@pytest.mark.asyncio
async def test_unchanged_policy_retains_revision_activation_and_grants(runtime_case: RuntimeCase) -> None:
    tool = approved_tool("read")
    policy = await replace_policy(runtime_case, (tool,))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)
    result = await runtime_case.bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=(tool,), native_identities=()))
    assert result.policy == policy
    assert result.changed_tools == result.revoked_grants == ()
    records = await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)
    assert len(records) == 1
    assert "owner-token" not in records[0].model_dump_json()


@pytest.mark.asyncio
async def test_schema_change_resets_only_changed_tool_choices(runtime_case: RuntimeCase) -> None:
    first, second = approved_tool("read"), approved_tool("write")
    policy = await replace_policy(runtime_case, (first, second))
    for name in ("read", "write"):
        await enable_tool(runtime_case, name)
    await save_matches(runtime_case, policy)
    changed = first.model_copy(update={"input_schema": {"type": "object"}})
    result = await runtime_case.bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=(changed, second), native_identities=()))
    assert result.changed_tools == ("read",)
    assert [(item.group_id, item.capability_key) for item in result.revoked_grants] == [("team", "read")]
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()
    await save_matches(runtime_case, result.policy)
    records = await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)
    assert tuple(record.tool.identity.downstream_name for record in records) == ("write",)


@pytest.mark.asyncio
async def test_policy_compare_and_swap_and_explicit_empty_contract(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, ())
    assert policy.tools == ()
    with pytest.raises(PersonalToolPolicyConflict):
        await runtime_case.bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(), native_identities=()))
    recreated = await create_downstream_mcp_stores("runtime-secret", runtime_case.database)
    assert await recreated.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal")) == policy


@pytest.mark.asyncio
async def test_policy_fault_rolls_back_permission_and_projection_changes(runtime_case: RuntimeCase) -> None:
    tool = approved_tool("read")
    policy = await replace_policy(runtime_case, (tool,))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)

    def fail(phase: str) -> None:
        if phase == "personal_tool_policy_saved":
            raise RuntimeError("injected")

    store = PersonalToolPolicyStoreService(runtime_case.database, lambda: runtime_case.query.now, fail)
    with pytest.raises(RuntimeError, match="injected"):
        await store.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=(), native_identities=()))
    assert await runtime_case.bundle.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal")) == policy
    assert len(await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ("disable", "disconnect", "configuration", "unpublish", "connector_grant", "delete", "rotate", "policy"))
async def test_stale_observation_save_rejects_revocation(runtime_case: RuntimeCase, revocation: str) -> None:
    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    command = await save_matches(runtime_case, policy)
    if revocation == "disable":
        await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False))
    elif revocation == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif revocation == "configuration":
        from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthConfigurationQuery, PersonalOAuthSettings, PreconfiguredPublicOAuthClient, ReplacePersonalOAuthConfiguration
        configuration = await runtime_case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))
        await runtime_case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(connector_id="personal", expected_revision=configuration.policy.revision, settings=PersonalOAuthSettings(requested_scopes=("different",), client=PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example", client_id="client"))))
    elif revocation == "unpublish":
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    elif revocation == "connector_grant":
        async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.delete(CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))
    elif revocation == "delete":
        await runtime_case.bundle.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    elif revocation == "rotate":
        from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import install_authorization
        from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
        await install_authorization(runtime_case, authorize_personal_grant(runtime_case.grant.model_copy(update={"access_token": SecretStr("rotated")})))
    else:
        await replace_policy(runtime_case, ())
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.bundle.personal_tool_access.save_observation(command)
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()


@pytest.mark.asyncio
async def test_connector_and_capability_grants_are_both_required(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    await save_matches(runtime_case, policy)
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()
    await enable_tool(runtime_case, "read")
    assert len(await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)) == 1
    async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.delete(CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()


@pytest.mark.asyncio
async def test_admission_rejects_foreign_identity_and_stale_fingerprint(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)
    identity = CapabilityIdentity(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read")
    command = AdmitPersonalTool(query=runtime_case.query, identity=identity, contract_revision=policy.revision, fingerprint=contract_fingerprint(policy.tools[0]))
    assert (await runtime_case.bundle.personal_tool_access.admit(command)).tool == policy.tools[0]
    for invalid in (command.model_copy(update={"fingerprint": "0" * 64}), command.model_copy(update={"identity": identity.model_copy(update={"capability_kind": "prompt"})}), command.model_copy(update={"identity": identity.model_copy(update={"connector_id": "foreign"})})):
        with pytest.raises(PersonalRuntimeUnavailable):
            await runtime_case.bundle.personal_tool_access.admit(invalid)


class InventoryTransport:
    def __init__(self, tools: tuple[DiscoveredTool, ...]) -> None:
        self._tools = tools

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        return PersonalToolInventory(tools=self._tools)


@pytest.mark.asyncio
async def test_discovery_keeps_private_metadata_out_of_global_catalogue(runtime_case: RuntimeCase) -> None:
    tool = approved_tool("read")
    policy = await replace_policy(runtime_case, (tool,))
    await enable_tool(runtime_case, "read")
    private = tool.model_copy(update={"title": "Private title", "description": "Private description"})
    service = PersonalToolDiscoveryService(runtime_case.bundle.personal_tool_policies, runtime_case.store, runtime_case.bundle.personal_tool_access, InventoryTransport((private, approved_tool("unapproved"))), lambda: runtime_case.query.now)
    result = await service.discover(runtime_case.query)
    assert result.matched_count == 1
    catalog = await runtime_case.bundle.catalogs.get(ConnectorIdQuery(connector_id="personal"))
    assert "Private" not in catalog.model_dump_json()
    assert "unapproved" not in result.model_dump_json()
    assert (await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query))[0].tool == policy.tools[0]


@pytest.mark.asyncio
async def test_observation_cannot_be_saved_for_foreign_owner_or_after_expiry(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    command = await save_matches(runtime_case, policy)
    foreign = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="other"), connector_id="personal")
    for query in (runtime_case.query.model_copy(update={"key": foreign}), runtime_case.query.model_copy(update={"now": command.target.expires_at + timedelta(seconds=1)})):
        with pytest.raises(PersonalRuntimeUnavailable):
            await runtime_case.bundle.personal_tool_access.save_observation(command.model_copy(update={"query": query}))


@pytest.mark.parametrize("schema", ({"$ref": "https://evil.example/schema"}, {"$dynamicRef": "file:///tmp/schema"}, {"$schema": "http://json-schema.org/draft-07/schema#"}, {"$id": "https://evil.example/", "$ref": "#x"}))
def test_contract_rejects_external_schema_resolution(schema: dict[str, object]) -> None:
    with pytest.raises(PersonalToolPolicyInvalid):
        validate_contract_schema(schema)


def test_fingerprint_ignores_private_labels_but_tracks_execution_and_schema() -> None:
    tool = approved_tool("read")
    assert contract_fingerprint(tool) == contract_fingerprint(tool.model_copy(update={"title": "Private", "description": "Private"}))
    assert contract_fingerprint(tool) != contract_fingerprint(tool.model_copy(update={"execution": {"taskSupport": "required"}}))
    validate_arguments(tool, {"value": "ok"})
    with pytest.raises(ValidationError):
        validate_arguments(tool, {"value": 1})
    with pytest.raises(ValidationError):
        validate_arguments(tool, {})


@pytest.mark.asyncio
async def test_two_principals_keep_distinct_inventories_and_reject_cipher_transplant(runtime_case: RuntimeCase) -> None:
    from umbod.core.connectors.downstream_mcp.personal_connections import ReplacePersonalAuthorization
    from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
    from umbod.core.connectors.downstream_mcp.stores.personal_tools_schema import PERSONAL_TOOL_OBSERVATION_TABLE, PersonalToolObservationRecordKey

    first, second = approved_tool("read"), approved_tool("write")
    await replace_policy(runtime_case, (first, second))
    for name in ("read", "write"):
        await enable_tool(runtime_case, name)
    other_key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="other"), connector_id="personal")
    other_connection = await runtime_case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=other_key, enabled=True))
    other_grant = runtime_case.grant.model_copy(update={"key": other_key, "access_token": SecretStr("other-token")})
    await runtime_case.bundle.personal_connections.replace_authorization(ReplacePersonalAuthorization(key=other_key, expected_revision=other_connection.revision, authorization=authorize_personal_grant(other_grant)))
    other_query = runtime_case.query.model_copy(update={"key": other_key})
    for query, tool in ((runtime_case.query, first), (other_query, second)):
        await PersonalToolDiscoveryService(runtime_case.bundle.personal_tool_policies, runtime_case.store, runtime_case.bundle.personal_tool_access, InventoryTransport((tool,)), lambda: runtime_case.query.now).discover(query)
    assert tuple(record.tool.identity.downstream_name for record in await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)) == ("read",)
    assert tuple(record.tool.identity.downstream_name for record in await runtime_case.bundle.personal_tool_access.list_available(other_query)) == ("write",)
    async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        rows = await session.find_many(PERSONAL_TOOL_OBSERVATION_TABLE, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))
        first_row = next(row for row in rows if row.subject == "owner")
        other_row = next(row for row in rows if row.subject == "other")
        await session.upsert(PERSONAL_TOOL_OBSERVATION_TABLE, UpsertCommand(key=PersonalToolObservationRecordKey(namespace=other_row.namespace, subject=other_row.subject, connector_id=other_row.connector_id), row=other_row.model_copy(update={"document": first_row.document})))
    assert await runtime_case.bundle.personal_tool_access.list_available(other_query) == ()


@pytest.mark.asyncio
async def test_live_schema_difference_does_not_match_approved_tool(runtime_case: RuntimeCase) -> None:
    tool = approved_tool("read")
    await replace_policy(runtime_case, (tool,))
    await enable_tool(runtime_case, "read")
    changed = tool.model_copy(update={"input_schema": {}})
    result = await PersonalToolDiscoveryService(runtime_case.bundle.personal_tool_policies, runtime_case.store, runtime_case.bundle.personal_tool_access, InventoryTransport((changed,)), lambda: runtime_case.query.now).discover(runtime_case.query)
    assert result.matched_count == 0
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()


@pytest.mark.asyncio
async def test_collision_with_unpublished_connector_or_native_tool_is_denied(runtime_case: RuntimeCase) -> None:
    from umbod.core.capabilities.tools.names import PublicToolIdentity
    from umbod.core.connectors.downstream_mcp.models import StaticBearerConnectorDefinition, ToolCatalogSnapshot
    from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog, SaveConnectorDefinition

    tool = approved_tool("read")
    other = StaticBearerConnectorDefinition(connector_id="other", display_name="Personal", endpoint_url="https://other.example/mcp", tool_name_prefix="Personal")
    await runtime_case.bundle.definitions.save(SaveConnectorDefinition(definition=other))
    await runtime_case.bundle.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id="other", discovered_at=runtime_case.query.now, tools=(tool.model_copy(update={"identity": ToolIdentity(connector_id="other", downstream_name="read")}),))))
    command = ReplacePersonalToolPolicy(connector_id="personal", expected_revision="unconfigured", tools=(tool,), native_identities=())
    with pytest.raises(PersonalToolPolicyInvalid):
        await runtime_case.bundle.personal_tool_policies.replace(command)
    await runtime_case.bundle.catalogs.delete(ConnectorIdQuery(connector_id="other"))
    with pytest.raises(PersonalToolPolicyInvalid):
        await runtime_case.bundle.personal_tool_policies.replace(command.model_copy(update={"native_identities": (PublicToolIdentity(connector_id="native", tool_name_prefix="Personal", operation_name="read"),)}))


@pytest.mark.asyncio
async def test_noop_restores_only_missing_projection_without_reenabling_tool(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    await runtime_case.bundle.catalogs.delete(ConnectorIdQuery(connector_id="personal"))
    result = await runtime_case.bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=policy.tools, native_identities=()))
    assert result.policy == policy
    assert result.changed_tools == result.revoked_grants == ()
    assert await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query) == ()
    assert (await runtime_case.bundle.catalogs.get(ConnectorIdQuery(connector_id="personal"))).snapshot.tools == policy.tools


@pytest.mark.asyncio
async def test_policy_concurrent_compare_and_swap_has_exactly_one_winner(runtime_case: RuntimeCase) -> None:
    policy = await replace_policy(runtime_case, ())
    outcomes = await asyncio.gather(*(runtime_case.bundle.personal_tool_policies.replace(ReplacePersonalToolPolicy(connector_id="personal", expected_revision=policy.revision, tools=(approved_tool(name),), native_identities=())) for name in ("read", "write")), return_exceptions=True)
    assert sum(isinstance(result, PersonalToolPolicyConflict) for result in outcomes) == 1


@pytest.mark.asyncio
async def test_aggregate_delete_fault_restores_policy_and_owner_observation(runtime_case: RuntimeCase) -> None:
    from umbod.core.configuration.persistence import AuthenticatedTextCipher
    from umbod.core.connectors.downstream_mcp.management import DownstreamConnectorUnitOfWorkService

    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)

    def fail(phase: str) -> None:
        if phase == "definition":
            raise RuntimeError("injected")

    unit_of_work = DownstreamConnectorUnitOfWorkService(runtime_case.database, AuthenticatedTextCipher("runtime-secret"), fail, lambda: runtime_case.query.now)
    with pytest.raises(RuntimeError, match="injected"):
        await unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    assert await runtime_case.bundle.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal")) == policy
    assert len(await runtime_case.bundle.personal_tool_access.list_available(runtime_case.query)) == 1


@pytest.mark.asyncio
async def test_observations_survive_worker_recreation(runtime_case: RuntimeCase, tmp_path: Path) -> None:
    from tests.persistence_runtime import prepared_sqlite_runtime

    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)
    path = tmp_path / "runtime.sqlite3"
    database = (await prepared_sqlite_runtime(path)).database if path.exists() else runtime_case.database
    recreated = await create_downstream_mcp_stores("runtime-secret", database)
    assert len(await recreated.personal_tool_access.list_available(runtime_case.query)) == 1


@pytest.mark.asyncio
async def test_discovery_rechecks_time_after_network(runtime_case: RuntimeCase) -> None:
    tool = approved_tool("read")
    await replace_policy(runtime_case, (tool,))
    service = PersonalToolDiscoveryService(runtime_case.bundle.personal_tool_policies, runtime_case.store, runtime_case.bundle.personal_tool_access, InventoryTransport((tool,)), lambda: runtime_case.query.now + timedelta(hours=2))
    with pytest.raises(PersonalRuntimeUnavailable):
        await service.discover(runtime_case.query)


def test_local_schema_references_and_explicit_empty_output_contract() -> None:
    from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithOutputSchema
    from umbod.core.connectors.downstream_mcp.personal_tools import validate_output

    tool = approved_tool("read")
    local = tool.model_copy(update={"input_schema": {"$defs": {"value": {"type": "string"}}, "type": "object", "properties": {"value": {"$ref": "#/$defs/value"}}, "required": ["value"]}})
    validate_arguments(local, {"value": "valid"})
    with pytest.raises(ValidationError):
        validate_arguments(local, {"value": 42})
    present = DiscoveredToolWithOutputSchema(**tool.model_dump(exclude={"output_schema_status"}), output_schema={})
    assert contract_fingerprint(present) != contract_fingerprint(tool)
    validate_output(present, {})


@pytest.mark.asyncio
async def test_personal_publication_checks_approved_names_but_allows_catalogue_free(runtime_case: RuntimeCase) -> None:
    from umbod.core.capabilities.tools.names import PublicToolIdentity, PublicToolNameConflictError
    from umbod.core.connectors.downstream_mcp.management.queries import DownstreamConnectorQueries
    from umbod.core.connectors.downstream_mcp.publishing.service import DownstreamConnectorPublisher

    class Events:
        async def append(self, event: object) -> None:
            pass

    class NativeIdentities:
        async def identities(self) -> tuple[PublicToolIdentity, ...]:
            return (PublicToolIdentity(connector_id="native", tool_name_prefix="Personal", operation_name="read"),)

    bundle = runtime_case.bundle
    queries = DownstreamConnectorQueries(bundle.definitions, bundle.credentials, bundle.catalogs, bundle.health, bundle.publishing)
    publisher = DownstreamConnectorPublisher(bundle.publishing, Events(), queries, bundle.unit_of_work, NativeIdentities())
    await bundle.publishing.unpublish_connector("personal")
    await publisher.publish("personal")
    assert await bundle.publishing.is_published("personal")
    await replace_policy(runtime_case, (approved_tool("read"),))
    await bundle.publishing.unpublish_connector("personal")
    with pytest.raises(PublicToolNameConflictError):
        await publisher.publish("personal")
    assert not await bundle.publishing.is_published("personal")


@pytest.mark.asyncio
async def test_detached_inmemory_unit_of_work_snapshots_personal_tool_stores(runtime_case: RuntimeCase, tmp_path: Path) -> None:
    from umbod.core.connectors.downstream_mcp.management import InMemoryDownstreamConnectorUnitOfWork

    if (tmp_path / "runtime.sqlite3").exists():
        pytest.skip("Detached unit of work is an in-memory adapter")
    bundle = runtime_case.bundle
    policy = await replace_policy(runtime_case, (approved_tool("read"),))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)

    def fail(phase: str) -> None:
        if phase == "definition":
            raise RuntimeError("injected")

    unit_of_work = InMemoryDownstreamConnectorUnitOfWork(bundle.definitions, bundle.credentials, bundle.catalogs, bundle.health, bundle.activations, bundle.publishing, fail, bundle.personal_connections, bundle.personal_oauth_configurations, bundle.personal_tool_policies, bundle.personal_tool_access)
    with pytest.raises(RuntimeError, match="injected"):
        await unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    assert await bundle.personal_tool_policies.get(ConnectorIdQuery(connector_id="personal")) == policy
    assert len(await bundle.personal_tool_access.list_available(runtime_case.query)) == 1
