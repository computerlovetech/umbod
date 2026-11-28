from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import jwt
import pytest
import pytest_asyncio
from fastmcp import Context, FastMCP
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.google import GoogleProvider, GoogleTokenVerifier
from fastmcp.server.middleware import MiddlewareContext
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import AppConfig, load_app_config_without_env_file
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.downstream_mcp.personal.connections import PersonalCaller
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.core.persistence import PersistenceRuntime
from umbod.core.system_settings.provider_group_mappings import ProviderGroupMapping, create_provider_group_mappings_service
from umbod.mcp.auth.factory import MCPAuthProviderFactory
from umbod.mcp.auth.membership import McpGroupMembership
from umbod.mcp.connectors.downstream_mcp.permissions import GroupDownstreamToolPermissionPolicy
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider
from umbod.mcp.connectors.native.tools.infrastructure.dependencies import get_allowed_connector_tool_refs
from umbod.mcp.connectors.openapi.deps import capture_openapi_groups
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, StaticFilesystemGroupClaimFields
from umbod.mcp.public_app import build_mcp

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


@pytest.mark.asyncio
async def test_public_mcp_uses_one_live_snapshot_across_access_adapters(
    persistence: PersistenceRuntime, entra_settings: AppConfig,
) -> None:
    settings = entra_settings
    settings_service = create_provider_group_mappings_service(persistence.database)
    groups = create_group_management(persistence.database)
    await groups.register_group(RegisterGroup(group_id="internal"))
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=(_PERMISSION_CLAIM, "roles"))
    permissions.grant_tool("internal", "connector", "read")
    permissions.grant_tool("external", "connector", "inherited")
    permissions.grant_tool("unmatched-role", "connector", "other-claim")
    server = await build_test_server(settings, persistence, permissions)
    assert isinstance(server.auth, AzureProvider)
    membership = server.group_membership_resolver
    assert isinstance(membership, McpGroupMembership)
    assert server.middleware[0] is membership
    token = AccessToken(token="accepted", client_id="mcp-client", scopes=["read"], claims={
        "iss": _ISSUER, "sub": "member", "oid": "account", "tid": "tenant", "scp": "read",
        _PERMISSION_CLAIM: ["external", "internal"], "roles": ["unmatched-role"],
    })
    marker = auth_context_var.set(AuthenticatedUser(token))
    try:
        async with Context(server):
            filesystem = CurrentFilesystemCallerCapture(server, StaticFilesystemGroupClaimFields(_PERMISSION_CLAIM))
            downstream = GroupDownstreamToolPermissionPolicy(permissions, membership)

            async def check_snapshot(_context: MiddlewareContext[None]) -> None:
                assert filesystem.capture().groups.group_ids == ("internal",)
                captured = downstream.capture()
                assert captured.allows("connector", "read")
                assert not captured.allows("connector", "other-claim")
                await groups.delete_group("internal")
                assert capture_openapi_groups(server).group_ids == ("internal",)
                assert get_allowed_connector_tool_refs().allows(ConnectorToolRef("connector", "read"))
                personal = await McpPersonalCallerProvider(settings, membership).get_caller()
                assert isinstance(personal, PersonalCaller)
                assert personal.groups.group_ids == ("internal",)

            async def check_no_membership(_context: MiddlewareContext[None]) -> None:
                assert filesystem.capture().groups.group_ids == ()
                captured = downstream.capture()
                assert not captured.allows("connector", "inherited")
                assert not captured.allows("connector", "other-claim")
                assert not captured.allows("connector", "read")

            context = MiddlewareContext(message=None, method="tools/list")
            await membership.on_message(context, check_no_membership)
            await settings_service.replace("administrator", (_GROUP_RULE,))
            await membership.on_message(context, check_snapshot)
            await membership.on_message(context, check_no_membership)
            await settings_service.reset("administrator")
            await membership.on_message(context, check_no_membership)
            assert filesystem.capture().groups.group_ids == ()
    finally:
        auth_context_var.reset(marker)


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

            await server.group_membership_resolver.on_message(
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
    membership = server.group_membership_resolver

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
