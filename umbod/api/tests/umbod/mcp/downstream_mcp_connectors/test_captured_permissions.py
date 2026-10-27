import asyncio
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.tools import ToolResult

from tests.umbod.mcp.downstream_mcp_connectors.test_provider import _downstream, _provider
from umbod.core.callers import AuthenticationProvenance, CallerContext, UnavailableSubject
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation import ConnectorInvocation, PermitAllConnectorInvocationPolicy
from umbod.core.permissions import ConnectorCapabilityPermission, InMemoryGroupConnectorToolPermissions
from umbod.mcp.connectors.downstream_mcp import GroupDownstreamToolPermissionPolicy, UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.connectors.downstream_mcp import permissions as permission_boundary
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolRecord
from umbod.core.connectors.downstream_mcp.stores import ToolCatalogFound
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoverySnapshot


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
@pytest.mark.parametrize("operation", ["tools", "search", "resources", "templates", "prompts", "access"])
async def test_listing_io_cannot_switch_captured_caller(
    monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    provider, _, _, _, _ = await _provider({"weather": _downstream(), "calendar": _downstream()})
    token = SimpleNamespace(claims={"sub": "alice", "groups": ["engineering"]})
    read_token = Mock(return_value=token)
    monkeypatch.setattr(permission_boundary, "get_access_token", read_token)
    provider._permission_policy = GroupDownstreamToolPermissionPolicy(_permissions())
    original_catalogs = provider._eligible_catalogs

    async def list_and_mutate() -> tuple[PersonalToolRecord, ...]:
        token.claims["groups"] = ["support"]
        return ()

    async def catalogs_and_mutate(snapshot: DownstreamDiscoverySnapshot) -> list[tuple[str, ToolCatalogFound]]:
        token.claims["groups"] = ["support"]
        return await original_catalogs(snapshot)

    monkeypatch.setattr(provider._personal_runtime, "list_tools", list_and_mutate)
    monkeypatch.setattr(provider, "_eligible_catalogs", catalogs_and_mutate)
    if operation == "tools":
        assert [tool.name for tool in await provider.list_tools()] == ["weather_forecast"]
    elif operation == "search":
        assert [candidate.tool_name for candidate in await provider.eligible_search_candidates()] == ["weather_forecast"]
    elif operation == "resources":
        assert [str(resource.uri) for resource in await provider.list_resources()] == ["data://weather/weather"]
    elif operation == "templates":
        assert [template.uri_template for template in await provider.list_resource_templates()] == ["data://weather/{city}"]
    elif operation == "prompts":
        assert [prompt.name for prompt in await provider.list_prompts()] == ["weather_weather_prompt"]
    else:
        original_get = provider._stores.definitions.get

        async def get_and_mutate(query: object) -> object:
            token.claims["groups"] = ["support"]
            return await original_get(query)

        monkeypatch.setattr(provider._stores.definitions, "get", get_and_mutate)
        await provider._ensure_capability_access(CapabilityIdentity(connector_kind="downstream_mcp", connector_id="weather", capability_kind="tool", capability_key="forecast"))
    read_token.assert_called_once_with()


@pytest.mark.asyncio
async def test_listing_capture_does_not_freeze_grants_during_io(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _, _, _, _ = await _provider({"weather": _downstream()})
    permissions = _permissions()
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: SimpleNamespace(claims={"groups": ["engineering"]}))
    provider._permission_policy = GroupDownstreamToolPermissionPolicy(permissions)
    async def list_and_revoke() -> tuple[PersonalToolRecord, ...]:
        permissions.replace_group_permissions({}, {})
        return ()

    monkeypatch.setattr(provider._personal_runtime, "list_tools", list_and_revoke)

    assert await provider.list_tools() == []


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
async def test_held_tool_recaptures_changed_caller_after_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    token = SimpleNamespace(claims={"groups": ["engineering"]})
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: token)
    provider, factory, _, _, _ = await _provider({"weather": _downstream()})
    provider._permission_policy = GroupDownstreamToolPermissionPolicy(_permissions())
    held = await provider.get_tool("weather_forecast")
    assert held is not None

    async def approve_and_switch_caller(policy: PermitAllConnectorInvocationPolicy, invocation: ConnectorInvocation) -> None:
        token.claims["groups"] = ["support"]

    monkeypatch.setattr(PermitAllConnectorInvocationPolicy, "evaluate", approve_and_switch_caller)
    public = FastMCP("public")

    @public.tool
    async def invoke_held() -> ToolResult:
        return await held.run({"city": "Copenhagen"})

    async with Client(public) as client:
        result = await client.call_tool_mcp("invoke_held", {})

    assert result.is_error
    assert factory.created == []


@pytest.mark.asyncio
async def test_held_template_cached_resource_recaptures_changed_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    token = SimpleNamespace(claims={"groups": ["engineering"]})
    monkeypatch.setattr(permission_boundary, "get_access_token", lambda: token)
    provider, factory, _, _, _ = await _provider({"weather": _downstream()})
    provider._permission_policy = GroupDownstreamToolPermissionPolicy(_permissions())
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
