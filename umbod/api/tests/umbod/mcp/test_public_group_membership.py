import asyncio
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import jwt
import pytest
import pytest_asyncio
from fastmcp import Client, Context, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.google import GoogleProvider, GoogleTokenVerifier
from fastmcp.server.dependencies import fastmcp_request_ctx
from fastmcp.server.middleware import MiddlewareContext
from mcp.shared.exceptions import MCPError
from mcp.types import PromptReference
from starlette.types import ASGIApp
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import AppConfig, load_app_config_without_env_file
from umbod.config.group_membership import ConfiguredGroupMembershipSource
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.callers import GroupMembership
from umbod.core.callers.membership import GroupMembershipResolver
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, NoAuthCredentialState, ToolCatalogSnapshot, ToolIdentity
from umbod.core.connectors.downstream_mcp.stores import ReplaceToolCatalog, SaveConnectorDefinition, SaveCredential, create_downstream_mcp_stores
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess
from umbod.infrastructure import create_filesystem_namespace_management
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.downstream_mcp.personal.connections import PersonalCaller
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.core.persistence import PersistenceRuntime
from umbod.core.system_settings.provider_group_mappings import ProviderGroupMapping, create_provider_group_mappings_service
from umbod.mcp.auth.factory import MCPAuthProviderFactory
from umbod.mcp.auth.membership import McpCallerSnapshotMiddleware
from umbod.mcp.connectors.downstream_mcp.permissions import GroupDownstreamToolPermissionPolicy
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider
from umbod.mcp.connectors.native.tools.infrastructure.dependencies import get_allowed_connector_tool_refs
from umbod.mcp.connectors.openapi.deps import capture_openapi_groups
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, RuntimeFilesystemGroupClaimFields, StaticFilesystemGroupClaimFields
from umbod.mcp.messaging import RuntimeProjectionHealth
from umbod.mcp.public_app import DynamicPublicMcpDispatcher, build_mcp

_ISSUER = "https://login.microsoftonline.com/tenant/v2.0"
_PERMISSION_CLAIM = "permission_groups"
_GROUP_RULE = ProviderGroupMapping(external_value="external", group_id="internal")


@pytest.fixture
def entra_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    environment = {
        "UMBOD_PROFILE": "production",
        "UMBOD_AUTH": "entra",
        "UMBOD_ROOT_SECRET": "provider-mapping-test-root-secret",
        "UMBOD_OIDC_CLIENT_ID": "mcp-client",
        "UMBOD_OIDC_CLIENT_SECRET": "mcp-secret",
        "UMBOD_OIDC_TENANT_ID": "tenant",
        "UMBOD_OIDC_REQUIRED_SCOPES": "read",
        "UMBOD_OIDC_ISSUER_URL": _ISSUER,
        "UMBOD_OIDC_AUDIENCE": "mcp-client",
        "UMBOD_MCP_PERMISSION_CLAIM": _PERMISSION_CLAIM,
        "UMBOD_ADMIN_MEMBERSHIP_CLAIM": "roles",
        "UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE": "example",
        "UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED": "false",
        "UMBOD_DATA_DIR": str(tmp_path),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return load_app_config_without_env_file()


@pytest_asyncio.fixture
async def persistence() -> AsyncIterator[PersistenceRuntime]:
    runtime = create_inmemory_runtime()
    try:
        await runtime.readiness.ensure_ready()
        yield runtime
    finally:
        await runtime.shutdown()


async def build_test_server(
    settings: AppConfig, persistence: PersistenceRuntime,
    permissions: InMemoryGroupConnectorToolPermissions,
) -> FastMCP:
    provider = MCPAuthProviderFactory().create(settings)
    connectors = ConnectorRuntime(
        connector_registrations=[], connector_configuration_store=None,
        connector_publishing_store=None, connector_tool_mappings=[],
    )
    return await build_mcp(settings, provider, connectors, persistence, None, permissions)


def _wire_transport(app: ASGIApp, path: str) -> StreamableHttpTransport:
    asgi_transport = httpx2.ASGITransport(app=app)

    def create_client(**options: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=asgi_transport, **options)

    return StreamableHttpTransport(
        f"http://localhost{path}", headers={"Authorization": "Bearer accepted"}, httpx_client_factory=create_client,
    )


def _count_wire_resolution(monkeypatch: pytest.MonkeyPatch) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    capture = ConfiguredGroupMembershipSource.capture
    resolve = GroupMembershipResolver.resolve_verified

    def observe(action: str) -> None:
        request = fastmcp_request_ctx.get()
        assert request is not None
        counts[request._srctx.method, action] += 1

    async def capture_rules(source: ConfiguredGroupMembershipSource) -> GroupMembershipResolver:
        observe("capture")
        return await capture(source)

    def resolve_groups(resolver: GroupMembershipResolver, claims: Mapping[str, object]) -> GroupMembership:
        observe("resolve")
        return resolve(resolver, claims)

    monkeypatch.setattr(ConfiguredGroupMembershipSource, "capture", capture_rules)
    monkeypatch.setattr(GroupMembershipResolver, "resolve_verified", resolve_groups)
    return counts


def _assert_wire_resolution(counts: Counter[tuple[str, str]], method: str, expected: int) -> None:
    assert (counts[method, "capture"], counts[method, "resolve"]) == (expected, expected)


def _register_tagged_capabilities(server: FastMCP) -> None:
    @server.tool(meta={"connector_id": "connector", "operation_name": "read"})
    async def connector_read() -> str:
        return "read"

    @server.prompt(meta={"connector_id": "connector", "capability_kind": "prompt", "capability_key": "connector_prompt"})
    async def connector_prompt(topic: str) -> str:
        return topic

    @server.resource("test://connector", meta={"connector_id": "connector", "capability_kind": "resource", "capability_key": "test://connector"})
    async def connector_resource() -> str:
        return "resource"

    @server.completion()
    async def complete(ref: PromptReference, argument: dict[str, str], context: dict[str, Any] | None) -> list[str]:
        return ["suggestion"]


async def _publish_shared_connector(settings: AppConfig, persistence: PersistenceRuntime) -> None:
    infrastructure = downstream_mcp_infrastructure_settings_from_app_config(settings)
    stores = await create_downstream_mcp_stores(infrastructure.credential_secret, persistence.database)
    await stores.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(
        connector_id="weather", display_name="Weather", tool_name_prefix="weather", endpoint_url="https://weather.example/mcp",
    )))
    await stores.credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id="weather")))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id="weather", discovered_at=datetime(2026, 1, 1, tzinfo=UTC), tools=(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id="weather", downstream_name="forecast"), title="Forecast",
            description="Current forecast", input_schema={"type": "object", "properties": {}},
        ),),
    )))
    await stores.publishing.publish_connector("weather")
    await stores.activations.set_status(CapabilityRef(
        connector_kind="downstream_mcp", connector_id="weather", capability_kind="tool", capability_key="forecast",
    ), ActivationStatus.ENABLED)


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_debug", [False, True])
async def test_public_http_messages_resolve_once_and_revocation_applies_on_open_session(
    persistence: PersistenceRuntime, entra_settings: AppConfig, monkeypatch: pytest.MonkeyPatch, auth_debug: bool,
) -> None:
    settings = entra_settings.model_copy(update={"mcp": entra_settings.mcp.model_copy(update={
        "auth_debug_enabled": auth_debug, "connector_tool_exposure_mode": "flat",
    })})
    await _publish_shared_connector(settings, persistence)
    await create_group_management(persistence.database).register_group(RegisterGroup(group_id="internal"))
    filesystems = create_filesystem_namespace_management(database=persistence.database, issuer=_ISSUER)
    namespace = await filesystems.create(CreateSharedNamespace(
        name="Shared reference", groups=[NamespaceGroupAccess(group_id="internal", access="read")],
    ))
    mapping = create_provider_group_mappings_service(persistence.database)
    await mapping.replace("administrator", (_GROUP_RULE,))
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=(_PERMISSION_CLAIM,))
    permissions.grant_tool("internal", "connector", "read")
    permissions.grant_tool("internal", "weather", "forecast")
    permissions.grant_capability("internal", "connector", "prompt", "connector_prompt")
    permissions.grant_capability("internal", "connector", "resource", "test://connector")
    server = await build_test_server(settings, persistence, permissions)
    await server.filesystem_discovery_runtime.reconcile()
    assert type(server.auth) is AzureProvider
    assert server.middleware[0] is server.caller_snapshot_middleware
    _register_tagged_capabilities(server)
    counts = _count_wire_resolution(monkeypatch)

    async def verify_token(value: str) -> AccessToken | None:
        if value != "accepted":
            return None
        return AccessToken(token=value, client_id="mcp-client", scopes=["read"], claims={
            "iss": _ISSUER, "sub": "member", "oid": "account", "tid": "tenant", "scp": "read",
            _PERMISSION_CLAIM: ["external", "internal"],
        })

    monkeypatch.setattr(server.auth, "verify_token", verify_token)
    app = server.http_app(path="/mcp", stateless_http=False, json_response=True)
    health = RuntimeProjectionHealth()
    health.ready = True
    dispatcher = DynamicPublicMcpDispatcher(app, server.downstream_mcp_discovery_runtime, health)
    transport = _wire_transport(dispatcher, "/mcp")
    scoped_transport = _wire_transport(dispatcher, "/mcp/proxies/weather")
    async with (
        app.router.lifespan_context(app),
        Client(transport, timeout=5, mode="legacy") as client,
        Client(scoped_transport, timeout=5, mode="legacy") as scoped,
    ):
        session_id = transport.get_session_id()
        assert session_id is not None
        visible_tools = {tool.name for tool in await client.list_tools()}
        assert {"connector_read", "get_filesystem_node", "weather_forecast"} <= visible_tools
        _assert_wire_resolution(counts, "tools/list", 1)
        scoped_tools = {tool.name for tool in await scoped.list_tools()}
        assert "forecast" in scoped_tools and "get_filesystem_node" not in scoped_tools
        _assert_wire_resolution(counts, "tools/list", 2)
        assert not (await client.call_tool("connector_read", {})).is_error
        _assert_wire_resolution(counts, "tools/call", 1)
        node_args = {"node_id": str(namespace.root_node_id)}
        assert not (await client.call_tool("get_filesystem_node", node_args)).is_error
        _assert_wire_resolution(counts, "tools/call", 2)

        assert "connector_prompt" in {prompt.name for prompt in await client.list_prompts()}
        assert (await client.get_prompt("connector_prompt", {"topic": "test"})).messages
        assert "test://connector" in {str(resource.uri) for resource in await client.list_resources()}
        assert (await client.read_resource("test://connector"))[0].text == "resource"
        for method in ("prompts/list", "prompts/get", "resources/list", "resources/read"):
            _assert_wire_resolution(counts, method, 1)

        if not auth_debug:
            ref = PromptReference(type="ref/prompt", name="connector_prompt")
            assert (await client.complete(ref, {"name": "topic", "value": ""})).values == ["suggestion"]
            _assert_wire_resolution(counts, "completion/complete", 1)

        await mapping.reset("administrator")
        visible_tools = {tool.name for tool in await client.list_tools()}
        assert not {"connector_read", "get_filesystem_node", "weather_forecast"} & visible_tools
        assert "filesystem_browse" in visible_tools
        _assert_wire_resolution(counts, "tools/list", 3)
        assert "forecast" not in {tool.name for tool in await scoped.list_tools()}
        _assert_wire_resolution(counts, "tools/list", 4)
        with pytest.raises(ToolError, match="insufficient permissions"):
            await client.call_tool("connector_read", {})
        _assert_wire_resolution(counts, "tools/call", 3)
        assert (await client.call_tool("get_filesystem_node", node_args, raise_on_error=False)).is_error
        _assert_wire_resolution(counts, "tools/call", 4)
        assert "connector_prompt" not in {prompt.name for prompt in await client.list_prompts()}
        with pytest.raises(MCPError):
            await client.get_prompt("connector_prompt", {"topic": "test"})
        assert "test://connector" not in {str(resource.uri) for resource in await client.list_resources()}
        with pytest.raises(MCPError):
            await client.read_resource("test://connector")
        for method in ("prompts/list", "prompts/get", "resources/list", "resources/read"):
            _assert_wire_resolution(counts, method, 2)

        if not auth_debug:
            assert not (await client.complete(ref, {"name": "topic", "value": ""})).values
            _assert_wire_resolution(counts, "completion/complete", 2)
        assert transport.get_session_id() == session_id


@pytest.mark.asyncio
async def test_public_mcp_uses_one_live_snapshot_across_access_adapters(
    persistence: PersistenceRuntime, entra_settings: AppConfig,
) -> None:
    settings = entra_settings
    settings_service = create_provider_group_mappings_service(persistence.database)
    groups = create_group_management(persistence.database)
    await groups.register_group(RegisterGroup(group_id="internal"))
    await groups.register_group(RegisterGroup(group_id="a-team"))
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=(_PERMISSION_CLAIM, "roles"))
    permissions.grant_tool("internal", "connector", "read")
    permissions.grant_tool("external", "connector", "inherited")
    permissions.grant_tool("unmatched-role", "connector", "other-claim")
    server = await build_test_server(settings, persistence, permissions)
    assert isinstance(server.auth, AzureProvider)
    membership = server.caller_snapshot_middleware
    assert isinstance(membership, McpCallerSnapshotMiddleware)
    assert server.middleware[0] is membership
    token = AccessToken(token="accepted", client_id="mcp-client", scopes=["read"], claims={
        "iss": _ISSUER, "sub": "member", "oid": "account", "tid": "tenant", "scp": "read",
        _PERMISSION_CLAIM: ["external", "internal"], "roles": ["unmatched-role"],
    })
    marker = auth_context_var.set(AuthenticatedUser(token))
    try:
        async with Context(server):
            filesystem = CurrentFilesystemCallerCapture(server, StaticFilesystemGroupClaimFields(_PERMISSION_CLAIM))
            downstream = GroupDownstreamToolPermissionPolicy(permissions, server)
            filesystem_runtime = CurrentFilesystemCallerCapture(server, RuntimeFilesystemGroupClaimFields(permissions))

            async def check_snapshot(context: MiddlewareContext[None]) -> None:
                snapshot = filesystem.capture()
                assert snapshot.groups.group_ids == ("a-team", "internal")
                assert membership.current(token) is snapshot
                assert filesystem_runtime.capture() is snapshot
                captured = downstream.capture()
                assert captured.allows("connector", "read")
                assert not captured.allows("connector", "other-claim")
                await groups.delete_group("internal")
                await membership.on_message(context, check_nested_snapshot)
                assert capture_openapi_groups(server) is snapshot.groups
                assert get_allowed_connector_tool_refs().allows(ConnectorToolRef("connector", "read"))
                personal = await McpPersonalCallerProvider(settings, server).get_caller()
                assert isinstance(personal, PersonalCaller)
                assert personal.caller is snapshot.caller
                assert personal.groups is snapshot.groups
                assert personal.principal.subject == "tenant:account"

                permissions.group_claim_fields = ("roles",)
                assert not filesystem_runtime.capture().groups.group_ids
                assert not downstream.capture().allows("connector", "read")
                assert not get_allowed_connector_tool_refs().allows(ConnectorToolRef("connector", "read"))
                assert capture_openapi_groups(server) is snapshot.groups
                assert filesystem.capture() is snapshot
                permissions.group_claim_fields = (_PERMISSION_CLAIM, "roles")

            async def check_nested_snapshot(_context: MiddlewareContext[None]) -> None:
                assert filesystem.capture().groups.group_ids == ("a-team", "internal")

            async def check_no_membership(_context: MiddlewareContext[None]) -> None:
                assert filesystem.capture().groups.group_ids == ()
                captured = downstream.capture()
                assert not captured.allows("connector", "inherited")
                assert not captured.allows("connector", "other-claim")
                assert not captured.allows("connector", "read")

            context = MiddlewareContext(message=None, method="tools/list")
            await membership.on_message(context, check_no_membership)
            await settings_service.replace("administrator", (
                _GROUP_RULE, ProviderGroupMapping(external_value="external", group_id="a-team"),
            ))
            await membership.on_message(context, check_snapshot)
            await groups.delete_group("a-team")
            await membership.on_message(context, check_no_membership)
            await settings_service.reset("administrator")
            await membership.on_message(context, check_no_membership)
            assert filesystem.capture().groups.group_ids == ()
    finally:
        auth_context_var.reset(marker)


@pytest.mark.asyncio
async def test_cancellation_clears_inherited_membership_without_affecting_another_caller(
    persistence: PersistenceRuntime, entra_settings: AppConfig,
) -> None:
    groups = create_group_management(persistence.database)
    await groups.register_group(RegisterGroup(group_id="first"))
    await groups.register_group(RegisterGroup(group_id="second"))
    mapping = create_provider_group_mappings_service(persistence.database)
    await mapping.replace("administrator", tuple(
        ProviderGroupMapping(external_value=f"external-{name}", group_id=name) for name in ("first", "second")
    ))
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=(_PERMISSION_CLAIM,))
    server = await build_test_server(entra_settings, persistence, permissions)
    first_ready = asyncio.Event()
    second_ready = asyncio.Event()
    cancelled = asyncio.Event()
    observations: list[tuple[str, ...]] = []

    async def inspect_inherited_binding() -> None:
        await cancelled.wait()
        observations.append(capture_openapi_groups(server).group_ids)

    async def open_message(subject: str, tasks: asyncio.TaskGroup) -> None:
        token = AccessToken(token=subject, client_id="mcp-client", scopes=["read"], claims={
            "iss": _ISSUER, "sub": subject, _PERMISSION_CLAIM: [f"external-{subject}"],
        })
        marker = auth_context_var.set(AuthenticatedUser(token))
        try:
            async with Context(server):
                async def check(_context: MiddlewareContext[None]) -> None:
                    assert capture_openapi_groups(server).group_ids == (subject,)
                    if subject == "first":
                        tasks.create_task(inspect_inherited_binding())
                        first_ready.set()
                        await asyncio.Event().wait()
                    else:
                        second_ready.set()
                        await cancelled.wait()
                        assert capture_openapi_groups(server).group_ids == (subject,)

                if subject == "first":
                    with pytest.raises(asyncio.CancelledError):
                        await server.caller_snapshot_middleware.on_message(MiddlewareContext(message=None), check)
                    observations.append(capture_openapi_groups(server).group_ids)
                    cancelled.set()
                else:
                    await server.caller_snapshot_middleware.on_message(MiddlewareContext(message=None), check)
                    observations.append(capture_openapi_groups(server).group_ids)
        finally:
            auth_context_var.reset(marker)

    async with asyncio.TaskGroup() as tasks:
        first = tasks.create_task(open_message("first", tasks))
        await first_ready.wait()
        tasks.create_task(open_message("second", tasks))
        await second_ready.wait()
        first.cancel()
    assert observations == [(), (), ()]


@pytest.mark.asyncio
async def test_google_normalized_claim_without_issuer_cannot_grant_groups(
    persistence: PersistenceRuntime, entra_settings: AppConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_AUTH", "google")
    monkeypatch.setenv("UMBOD_OIDC_ISSUER_URL", "https://accounts.google.com")
    monkeypatch.setenv("UMBOD_OIDC_REQUIRED_SCOPES", "openid")
    monkeypatch.setenv("UMBOD_MCP_PERMISSION_CLAIM", "email")
    settings = load_app_config_without_env_file()
    email = "member@example.test"
    await create_group_management(persistence.database).register_group(RegisterGroup(group_id="internal"))
    await create_provider_group_mappings_service(persistence.database).replace(
        "administrator", (ProviderGroupMapping(external_value=email, group_id="internal"),),
    )
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("email",))
    server = await build_test_server(settings, persistence, permissions)
    assert isinstance(server.auth, GoogleProvider)

    def google_response(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx2.Response(200, json={"aud": "mcp-client", "scope": "openid", "sub": "member", "email": email})
        assert request.url.host == "www.googleapis.com"
        return httpx2.Response(200, json={"email": email})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(google_response)) as client:
        token = await GoogleTokenVerifier(http_client=client, audience="mcp-client").verify_token("opaque")
    assert token is not None
    assert token.claims["email"] == email
    assert "iss" not in token.claims

    marker = auth_context_var.set(AuthenticatedUser(token))
    try:
        async with Context(server):
            async def check_snapshot(_context: MiddlewareContext[None]) -> None:
                assert capture_openapi_groups(server).group_ids == ()

            await server.caller_snapshot_middleware.on_message(
                MiddlewareContext(message=None, method="tools/list"), check_snapshot,
            )
    finally:
        auth_context_var.reset(marker)


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_recipe", ["none", "dev"])
async def test_public_mcp_without_upstream_oauth_never_reads_provider_rules(
    persistence: PersistenceRuntime, auth_recipe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", auth_recipe)
    monkeypatch.setenv("UMBOD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UMBOD_MCP_TEST_BEARER_TOKEN", jwt.encode(
        {"sub": "local", "email": "local@example.test", "groups": [_GROUP_RULE.external_value]},
        "", algorithm="none",
    ))
    monkeypatch.setenv("UMBOD_MCP_PERMISSION_CLAIM", "groups")
    settings = load_app_config_without_env_file()
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=(settings.mcp.permission_group_claim,))
    server = await build_test_server(settings, persistence, permissions)
    membership = server.caller_snapshot_middleware

    async def fail_capture(_source: object) -> None:
        pytest.fail("MCP without upstream OAuth must not capture provider rules")

    monkeypatch.setattr("umbod.config.group_membership.ConfiguredGroupMembershipSource.capture", fail_capture)
    if auth_recipe == "dev":
        assert server.auth is not None
        token = await server.auth.verify_token(settings.mcp.test_bearer_token)
        assert token is not None
        marker = auth_context_var.set(AuthenticatedUser(token))
    else:
        marker = auth_context_var.set(None)
    try:
        async with Context(server):
            async def check_snapshot(_context: MiddlewareContext[None]) -> None:
                expected = (_GROUP_RULE.external_value,) if auth_recipe == "dev" else ()
                assert capture_openapi_groups(server).group_ids == expected

            await membership.on_message(MiddlewareContext(message=None, method="tools/list"), check_snapshot)
    finally:
        auth_context_var.reset(marker)
