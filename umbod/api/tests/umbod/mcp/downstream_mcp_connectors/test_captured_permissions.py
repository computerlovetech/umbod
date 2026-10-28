import asyncio
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pytest_asyncio
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.tools import ToolResult

from tests.persistence_runtime import prepared_inmemory_runtime
from tests.umbod.mcp.downstream_mcp_connectors.test_provider import InMemoryServerClientFactory, _downstream
from tests.umbod.mcp.downstream_mcp_connectors.signal_support import invocation_signals
from umbod.core.activation import ActivationStatus, CapabilityRef, create_capability_activation_store
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate, DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, PromptArgument, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_CREDENTIAL_TABLE, CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE, ConnectorDefinitionFound, ConnectorDefinitionMissing, ConnectorDefinitionStoreService, ConnectorIdQuery, EncryptedCredentialStoreService, ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, ToolCatalogStoreService
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.mcp.connectors.downstream_mcp import ConnectorAwareDownstreamMcpToolProvider
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime, DownstreamDiscoveryStores, create_downstream_discovery_runtime
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import SignalToolExecutionPipelineFactory
from umbod.core.callers import AuthenticationProvenance, CallerContext, UnavailableSubject
from umbod.core.invocation import ConnectorInvocation, ConnectorInvocationPolicy, PermitAllConnectorInvocationPolicy
from umbod.core.permissions import ConnectorCapabilityPermission, InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.downstream_mcp import GroupDownstreamToolPermissionPolicy, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.connectors.downstream_mcp import permissions as permission_boundary
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_tools import DisabledPersonalToolRuntime, PersonalToolRecord, PersonalToolRuntime
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoverySnapshot


@pytest_asyncio.fixture
async def persistence_runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


class MutatingPersonalRuntime(DisabledPersonalToolRuntime):
    def __init__(self, mutate: Callable[[], None]) -> None:
        self.mutate = mutate

    async def list_tools(self) -> tuple[PersonalToolRecord, ...]:
        await asyncio.sleep(0)
        self.mutate()
        return ()


class MutatingDefinitionStore(ConnectorDefinitionStoreService):
    def __init__(self, database: Database, mutate: Callable[[], None]) -> None:
        super().__init__(database, CONNECTOR_DEFINITION_TABLE)
        self.mutate = mutate

    async def get(self, query: ConnectorIdQuery) -> ConnectorDefinitionFound | ConnectorDefinitionMissing:
        result = await super().get(query)
        self.mutate()
        return result


class MutatingDiscoveryRuntime:
    def __init__(self, runtime: DownstreamDiscoveryRuntime, mutate: Callable[[], None]) -> None:
        self.runtime = runtime
        self.mutate = mutate

    def capture(self) -> DownstreamDiscoverySnapshot:
        snapshot = self.runtime.capture()
        self.mutate()
        return snapshot

    async def reconcile(self) -> None:
        await self.runtime.reconcile()


class SwitchingInvocationPolicy:
    def __init__(self, mutate: Callable[[], None]) -> None:
        self.mutate = mutate

    async def evaluate(self, invocation: ConnectorInvocation) -> None:
        self.mutate()


async def _provider(
    persistence_runtime: PersistenceRuntime,
    servers: dict[str, FastMCP],
    permissions: InMemoryGroupConnectorToolPermissions,
    *,
    personal_runtime: PersonalToolRuntime,
    invocation_policy: ConnectorInvocationPolicy,
    definition_mutation: Callable[[], None],
    discovery_mutation: Callable[[], None],
) -> tuple[ConnectorAwareDownstreamMcpToolProvider, InMemoryServerClientFactory]:
    database = persistence_runtime.database
    definitions = ConnectorDefinitionStoreService(database, CONNECTOR_DEFINITION_TABLE)
    credentials = EncryptedCredentialStoreService(database, CONNECTOR_CREDENTIAL_TABLE, AuthenticatedTextCipher("test-key"))
    catalogs = ToolCatalogStoreService(database, TOOL_CATALOG_TABLE)
    publishing = ConnectorPublishingStoreService(database, PUBLICATION_STATE_TABLE)
    activations = await create_capability_activation_store(database)
    for connector_id in servers:
        await definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(connector_id=connector_id, display_name=connector_id, endpoint_url=f"https://{connector_id}.example/mcp")))
        await credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id=connector_id)))
        await catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
            connector_id=connector_id,
            discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
            tools=(DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id=connector_id, downstream_name="forecast"), title="Forecast", description="Detailed forecast", input_schema={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}),),
            prompts=(DiscoveredPrompt(name="weather_prompt", title="Weather prompt", description="Build a weather prompt", arguments=(PromptArgument(name="city", required=True),)),),
            resources=(DiscoveredResource(name="weather", title="Weather", description="Current weather", uri=f"data://{connector_id}/weather"),),
            resource_templates=(DiscoveredResourceTemplate(name="weather_city", title="Weather city", description="Weather by city", uri_template=f"data://{connector_id}/{{city}}"),),
        )))
        await publishing.publish_connector(connector_id)
        for capability_kind, capability_key in (("tool", "forecast"), ("prompt", "weather_prompt"), ("resource", f"data://{connector_id}/weather"), ("resource_template", f"data://{connector_id}/{{city}}")):
            await activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id=connector_id, capability_kind=capability_kind, capability_key=capability_key), ActivationStatus.ENABLED)
    discovery = create_downstream_discovery_runtime(DownstreamDiscoveryStores(definitions=definitions, credentials=credentials, catalogs=catalogs, publishing=publishing, activations=activations, descriptions=SystemConnectorCapabilityDescriptionOverrideStore()))
    await discovery.reconcile()
    factory = InMemoryServerClientFactory(servers)
    signals = invocation_signals(InMemoryMcpMetricsRecorder())
    provider = ConnectorAwareDownstreamMcpToolProvider(
        discovery_runtime=MutatingDiscoveryRuntime(discovery, discovery_mutation), personal_runtime=personal_runtime,
        definitions=MutatingDefinitionStore(database, definition_mutation), credentials=credentials,
        catalogs=catalogs, publishing=publishing, activations=activations,
        client_factory=factory, permission_policy=GroupDownstreamToolPermissionPolicy(permissions),
        connector_scope="", signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(signals, invocation_policy),
    )
    return provider, factory


def _permissions() -> InMemoryGroupConnectorToolPermissions:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions(
        {"engineering": ("weather",), "support": ("calendar",)},
        {
            group: (
                ConnectorCapabilityPermission(connector, "tool", "forecast"),
                ConnectorCapabilityPermission(connector, "prompt", "weather_prompt"),
                ConnectorCapabilityPermission(connector, "resource", f"data://{connector}/weather"),
                ConnectorCapabilityPermission(connector, "resource_template", f"data://{connector}/{{city}}"),
            )
            for group, connector in (("engineering", "weather"), ("support", "calendar"))
        },
    )
    return permissions


def test_capture_reads_one_token_and_next_capture_observes_next_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    token = SimpleNamespace(claims={"sub": "alice", "groups": ["engineering"]})
    read_token = Mock(return_value=token)
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)
    source = GroupDownstreamToolPermissionPolicy(_permissions())

    captured = source.capture()
    token.claims["sub"] = "bob"
    token.claims["groups"][:] = ["support"]

    assert captured.allows("weather", "forecast")
    assert captured.allows_capability("weather", "prompt", "weather_prompt")
    assert not captured.allows("calendar", "forecast")
    read_token.assert_called_once_with()
    next_captured = source.capture()
    assert not next_captured.allows("weather", "forecast")
    assert next_captured.allows("calendar", "forecast")
    assert read_token.call_count == 2


def test_captured_groups_still_evaluate_current_grant_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: SimpleNamespace(claims={"groups": ["engineering"]}))
    permissions = _permissions()
    captured = GroupDownstreamToolPermissionPolicy(permissions).capture()
    assert captured.allows("weather", "forecast")

    permissions.replace_group_permissions({}, {})

    assert not captured.allows("weather", "forecast")


@pytest.mark.parametrize("token", [None, SimpleNamespace(), SimpleNamespace(claims=[]), SimpleNamespace(claims={})])
def test_missing_or_malformed_authentication_does_not_grant_access(monkeypatch: pytest.MonkeyPatch, token: object) -> None:
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: token)

    assert not GroupDownstreamToolPermissionPolicy(_permissions()).capture().allows("weather", "forecast")


@pytest.mark.parametrize("authentication,expected", [
    (None, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    (object(), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    (object.__new__(SingleTestUserOAuthProvider), AuthenticationProvenance.LOCAL_TEST),
    (object.__new__(AzureProvider), AuthenticationProvenance.UPSTREAM_VERIFIED),
])
def test_capture_uses_same_token_and_actual_server_authentication(
    monkeypatch: pytest.MonkeyPatch, authentication: object, expected: AuthenticationProvenance,
) -> None:
    token = SimpleNamespace(claims={"sub": "alice", "iss": "https://declared.example", "groups": ["engineering"]})
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: token)
    monkeypatch.setattr(permission_boundary, "get_server", lambda: SimpleNamespace(auth=authentication))
    observe = Mock(wraps=permission_boundary.caller_context_from_access_token)
    monkeypatch.setattr(permission_boundary, "caller_context_from_access_token", observe)

    assert GroupDownstreamToolPermissionPolicy(_permissions()).capture().allows("weather", "forecast")

    observe.assert_called_once_with(token, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["tools", "search"])
async def test_listing_io_cannot_switch_captured_caller(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime, operation: str,
) -> None:
    token = SimpleNamespace(claims={"sub": "alice", "groups": ["engineering"]})
    read_token = Mock(return_value=token)
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)

    def switch_caller() -> None:
        token.claims["groups"] = ["support"]

    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream(), "calendar": _downstream()}, _permissions(),
        personal_runtime=MutatingPersonalRuntime(switch_caller),
        invocation_policy=PermitAllConnectorInvocationPolicy(),
        definition_mutation=lambda: None, discovery_mutation=lambda: None,
    )
    if operation == "tools":
        assert [tool.name for tool in await provider.list_tools()] == ["weather_forecast"]
    else:
        assert [candidate.tool_name for candidate in await provider.eligible_search_candidates()] == ["weather_forecast"]
    read_token.assert_called_once_with()
    assert factory.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["resources", "templates", "prompts"])
async def test_native_listing_snapshot_capture_cannot_switch_captured_caller(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime, operation: str,
) -> None:
    token = SimpleNamespace(claims={"sub": "alice", "groups": ["engineering"]})
    read_token = Mock(return_value=token)
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)

    def switch_caller() -> None:
        token.claims["groups"] = ["support"]

    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream(), "calendar": _downstream()}, _permissions(),
        personal_runtime=DisabledPersonalToolRuntime(),
        invocation_policy=PermitAllConnectorInvocationPolicy(),
        definition_mutation=lambda: None, discovery_mutation=switch_caller,
    )
    if operation == "resources":
        assert [str(resource.uri) for resource in await provider.list_resources()] == ["data://weather/weather"]
    elif operation == "templates":
        assert [template.uri_template for template in await provider.list_resource_templates()] == ["data://weather/{city}"]
    else:
        assert [prompt.name for prompt in await provider.list_prompts()] == ["weather_weather_prompt"]
    assert token.claims["groups"] == ["support"]
    read_token.assert_called_once_with()
    assert factory.created == []


@pytest.mark.asyncio
async def test_resource_access_io_cannot_switch_captured_caller(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime,
) -> None:
    token = SimpleNamespace(claims={"sub": "alice", "groups": ["engineering"]})
    read_token = Mock(return_value=token)
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)

    def switch_caller() -> None:
        token.claims["groups"] = ["support"]

    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream()}, _permissions(),
        personal_runtime=DisabledPersonalToolRuntime(),
        invocation_policy=PermitAllConnectorInvocationPolicy(),
        definition_mutation=switch_caller, discovery_mutation=lambda: None,
    )
    resource = (await provider.list_resources())[0]
    public = FastMCP("public")

    @public.tool
    async def read_weather() -> str:
        assert await resource.read()
        return "weather"

    read_token.reset_mock()
    async with Client(public) as client:
        result = await client.call_tool_mcp("read_weather", {})

    assert not result.is_error
    assert result.content[0].text == "weather"
    assert token.claims["groups"] == ["support"]
    read_token.assert_called_once_with()
    assert factory.created == ["weather"]


@pytest.mark.asyncio
async def test_template_creation_recaptures_caller_after_initial_access_io(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime,
) -> None:
    token = SimpleNamespace(claims={"groups": ["engineering"]})
    read_token = Mock(return_value=token)
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)
    reads_during_initial_access: list[int] = []

    def switch_caller() -> None:
        reads_during_initial_access.append(read_token.call_count)
        token.claims["groups"] = ["support"]

    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream()}, _permissions(),
        personal_runtime=DisabledPersonalToolRuntime(),
        invocation_policy=PermitAllConnectorInvocationPolicy(),
        definition_mutation=switch_caller, discovery_mutation=lambda: None,
    )
    template = (await provider.list_resource_templates())[0]
    read_token.reset_mock()

    with pytest.raises(ToolError, match="not available"):
        await template.create_resource("data://weather/Copenhagen", {"city": "Copenhagen"})

    assert reads_during_initial_access
    assert set(reads_during_initial_access) == {1}
    assert read_token.call_count == 2
    assert factory.created == []


@pytest.mark.asyncio
async def test_listing_capture_does_not_freeze_grants_during_io(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime,
) -> None:
    permissions = _permissions()
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: SimpleNamespace(claims={"groups": ["engineering"]}))

    def revoke() -> None:
        permissions.replace_group_permissions({}, {})

    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream()}, permissions,
        personal_runtime=MutatingPersonalRuntime(revoke),
        invocation_policy=PermitAllConnectorInvocationPolicy(),
        definition_mutation=lambda: None, discovery_mutation=lambda: None,
    )

    assert await provider.list_tools() == []
    assert factory.created == []


def test_caller_authentication_unavailable_guard_denies_even_with_granted_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: SimpleNamespace(claims={"groups": ["engineering"]}))
    monkeypatch.setattr(permission_boundary, "caller_context_from_access_token", lambda token, authentication: CallerContext(
        authentication=AuthenticationProvenance.UNAVAILABLE, subject=UnavailableSubject(kind="unavailable"),
    ))

    assert not GroupDownstreamToolPermissionPolicy(_permissions()).capture().allows("weather", "forecast")


def test_unrestricted_capture_does_not_require_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    read_token = Mock(side_effect=AssertionError("Unrestricted capture must not read authentication"))
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)

    captured = UnrestrictedDownstreamToolPermissionPolicy().capture()

    assert captured.allows("weather", "forecast")
    assert captured.allows_capability("weather", "prompt", "weather_prompt")
    read_token.assert_not_called()


@pytest.mark.asyncio
async def test_shared_capture_source_isolates_overlapping_callers(monkeypatch: pytest.MonkeyPatch) -> None:
    current: ContextVar[SimpleNamespace] = ContextVar("downstream_permission_test")
    monkeypatch.setattr(permission_boundary, "get_access_token", current.get)
    source = GroupDownstreamToolPermissionPolicy(_permissions())

    async def admitted(group: str, connector: str) -> bool:
        token = SimpleNamespace(claims={"groups": [group]})
        reset = current.set(token)
        try:
            captured = source.capture()
            token.claims["groups"] = []
            await asyncio.sleep(0)
            return captured.allows(connector, "forecast")
        finally:
            current.reset(reset)

    assert await asyncio.gather(admitted("engineering", "weather"), admitted("support", "calendar")) == [True, True]


@pytest.mark.asyncio
async def test_held_tool_recaptures_changed_caller_after_approval(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime,
) -> None:
    token = SimpleNamespace(claims={"groups": ["engineering"]})
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: token)

    def switch_caller() -> None:
        token.claims["groups"] = ["support"]

    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream()}, _permissions(),
        personal_runtime=DisabledPersonalToolRuntime(),
        invocation_policy=SwitchingInvocationPolicy(switch_caller),
        definition_mutation=lambda: None, discovery_mutation=lambda: None,
    )
    held = await provider.get_tool("weather_forecast")
    assert held is not None
    public = FastMCP("public")

    @public.tool
    async def invoke_held() -> ToolResult:
        return await held.run({"city": "Copenhagen"})

    async with Client(public) as client:
        result = await client.call_tool_mcp("invoke_held", {})

    assert result.is_error
    assert factory.created == []


@pytest.mark.asyncio
async def test_held_template_cached_resource_recaptures_changed_caller(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime,
) -> None:
    token = SimpleNamespace(claims={"groups": ["engineering"]})
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: token)
    provider, factory = await _provider(
        persistence_runtime, {"weather": _downstream()}, _permissions(),
        personal_runtime=DisabledPersonalToolRuntime(),
        invocation_policy=PermitAllConnectorInvocationPolicy(),
        definition_mutation=lambda: None, discovery_mutation=lambda: None,
    )
    template = (await provider.list_resource_templates())[0]
    public = FastMCP("public")

    @public.tool
    async def read_then_switch() -> str:
        resource = await template.create_resource("data://weather/Copenhagen", {"city": "Copenhagen"})
        assert await resource.read()
        token.claims["groups"] = ["support"]
        with pytest.raises(ToolError, match="not available"):
            await resource.read()
        return "denied"

    async with Client(public) as client:
        result = await client.call_tool_mcp("read_then_switch", {})

    assert not result.is_error
    assert result.content[0].text == "denied"
    assert factory.created == ["weather"]
