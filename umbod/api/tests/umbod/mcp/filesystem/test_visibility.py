import asyncio
from typing import Any, Literal
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx2
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from mcp.shared.exceptions import MCPError
from starlette.applications import Starlette

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.infrastructure import create_access_control_driver
from umbod.core.filesystem.authorization import FilesystemAuthorizationReader, FilesystemOperation
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, SaveSharedNamespace
from umbod.core.filesystem.namespaces.models import SharedNamespaceView
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.infrastructure import create_filesystem_namespace_management
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, StaticFilesystemGroupClaimFields, register_filesystem_tools
from umbod.mcp.filesystem.authorization import FilesystemToolVisibility, FilesystemVisibilityMiddleware
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.filesystem.links import FILE_RESOURCE_TEMPLATE, file_resource_uri
from umbod.mcp.filesystem.runtime import FilesystemDiscoveryRuntime

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id

BOOTSTRAP_TOOLS = {
    "filesystem_browse", "get_filesystem_node", "list_filesystem_children",
    "create_filesystem_file", "create_filesystem_directory", "filesystem_upload", "update_filesystem_node",
    "filesystem_begin_upload", "filesystem_complete_upload",
}
READ_TOOLS = {"filesystem_browse", "get_filesystem_node", "list_filesystem_children"}
INSPECT_TOOLS = {"filesystem_browse", "get_filesystem_node"}
FILE_READ_TOOLS = INSPECT_TOOLS


def select_caller(filesystem: FilesystemMcp, subject: str, groups: tuple[str, ...] = ()) -> None:
    filesystem.callers.current.set(caller_snapshot(
        subject, "https://issuer", groups, AuthenticationProvenance.UPSTREAM_VERIFIED,
    ))


async def listed_tools(filesystem: FilesystemMcp) -> set[str]:
    async with Client(filesystem.server) as client:
        return {tool.name for tool in await client.list_tools()}


async def private_node(filesystem: FilesystemMcp, kind: str = "file") -> UUID:
    async with Client(filesystem.server) as client:
        return UUID(await create_node(client, await root_id(client), str(uuid4()), kind))


async def shared_namespace(
    filesystem: FilesystemMcp, access: Literal["read", "read_write"] = "read_write",
) -> SharedNamespaceView:
    groups = create_group_management(filesystem.database)
    group_id = str(uuid4())
    await groups.register_group(RegisterGroup(group_id=group_id))
    management = create_filesystem_namespace_management(database=filesystem.database, issuer="https://issuer")
    return await management.create(CreateSharedNamespace(
        name="Shared reference", groups=[NamespaceGroupAccess(group_id=group_id, access=access)],
    ))


async def save_namespace_access(
    filesystem: FilesystemMcp, namespace: SharedNamespaceView, access: Literal["read", "read_write"] | None,
) -> SharedNamespaceView:
    management = create_filesystem_namespace_management(database=filesystem.database, issuer="https://issuer")
    return await management.save(namespace.id, SaveSharedNamespace(
        expected_revision=namespace.revision, name=namespace.name,
        groups=[] if access is None else [NamespaceGroupAccess(group_id=namespace.groups[0].group_id, access=access)],
    ))


@pytest.mark.asyncio
async def test_personal_namespace_exposes_directory_operations_without_retired_tools(filesystem_mcp: FilesystemMcp) -> None:
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [(), ("administrators",)])
async def test_no_namespace_access_hides_tools_even_for_administrators(
    filesystem_mcp: FilesystemMcp, groups: tuple[str, ...],
) -> None:
    select_caller(filesystem_mcp, "bob", groups)
    assert await listed_tools(filesystem_mcp) == {"filesystem_browse"}


@pytest.mark.asyncio
@pytest.mark.parametrize("access", ["read", "read_write"])
async def test_shared_namespace_access_controls_discovery(
    filesystem_mcp: FilesystemMcp, access: Literal["read", "read_write"],
) -> None:
    namespace = await shared_namespace(filesystem_mcp, access)
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob", (namespace.groups[0].group_id,))
    assert await listed_tools(filesystem_mcp) == (READ_TOOLS if access == "read" else BOOTSTRAP_TOOLS)


@pytest.mark.asyncio
async def test_personal_file_adds_read_delete_and_sharing_tools(filesystem_mcp: FilesystemMcp) -> None:
    await private_node(filesystem_mcp)
    await filesystem_mcp.runtime.reconcile()
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS | {"filesystem_delete_file", "filesystem_share", "filesystem_search_sharing_recipients"}


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.LOCAL_SEMANTIC,
])
async def test_unverified_identity_cannot_discover_filesystem_tools(
    filesystem_mcp: FilesystemMcp, provenance: AuthenticationProvenance,
) -> None:
    filesystem_mcp.callers.current.set(caller_snapshot("alice", "https://issuer", (), provenance))
    assert await listed_tools(filesystem_mcp) == set()


@pytest.mark.asyncio
async def test_concurrent_discovery_does_not_share_callers(filesystem_mcp: FilesystemMcp) -> None:
    async def discover(subject: str) -> set[str]:
        select_caller(filesystem_mcp, subject)
        return await listed_tools(filesystem_mcp)

    assert await asyncio.gather(discover("alice"), discover("bob")) == [BOOTSTRAP_TOOLS, {"filesystem_browse"}]


@pytest.mark.asyncio
async def test_connector_scoped_discovery_excludes_filesystem(filesystem_mcp: FilesystemMcp) -> None:
    token = _REQUEST_CONNECTOR_SCOPE.set("connector")
    try:
        assert await listed_tools(filesystem_mcp) == set()
    finally:
        _REQUEST_CONNECTOR_SCOPE.reset(token)


@pytest.mark.asyncio
async def test_discovery_after_hydration_never_reads_database_or_constructs_services(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = Mock(side_effect=AssertionError("Discovery performed I/O"))
    monkeypatch.setattr(filesystem_mcp.database, "read_session", forbidden)
    for method in ("browsing", "creation", "content", "deletion", "updates", "uploads", "access", "namespaces"):
        monkeypatch.setattr(filesystem_mcp.services, method, forbidden)
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_revoked_shared_namespace_rejects_retained_resource_before_discovery_refresh(
    filesystem_mcp: FilesystemMcp,
) -> None:
    filesystem = filesystem_mcp
    namespace = await shared_namespace(filesystem)
    select_caller(filesystem, "alice", (namespace.groups[0].group_id,))
    async with Client(filesystem.server) as client:
        node_id = await create_node(client, str(namespace.root_node_id), "shared.txt", "file")
    await filesystem.runtime.reconcile()
    select_caller(filesystem, "bob", (namespace.groups[0].group_id,))
    before = await listed_tools(filesystem)
    assert "filesystem_delete_file" in before
    await save_namespace_access(filesystem, namespace, None)
    assert await listed_tools(filesystem) == before
    async with Client(filesystem.server) as client:
        with pytest.raises(MCPError, match="filesystem_permission_denied"):
            await client.read_resource(file_resource_uri(UUID(node_id)))
    await filesystem.runtime.reconcile()
    assert await listed_tools(filesystem) == {"filesystem_browse"}


def http_transport(app: Starlette) -> StreamableHttpTransport:
    transport = httpx2.ASGITransport(app=app)

    def create_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=transport, **kwargs)

    return StreamableHttpTransport(
        "http://localhost/mcp", headers={"Authorization": "Bearer accepted"}, httpx_client_factory=create_client,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("subject,visible", [("alice", True), ("bob", False)])
async def test_http_lookup_enforces_personal_namespace_visibility_with_verified_identity(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, subject: str, visible: bool,
) -> None:
    filesystem = filesystem_mcp
    home = await filesystem.services.homes().get_or_provision(filesystem.callers.current.get())
    provider = GoogleProvider(
        client_id="client", client_secret="secret", base_url="http://localhost",
        jwt_signing_key="filesystem-test-signing-key",
    )
    verify = AsyncMock(return_value=AccessToken(
        token="accepted", client_id="client", scopes=provider.required_scopes,
        claims={"iss": "https://issuer", "sub": subject, "groups": []},
    ))
    monkeypatch.setattr(provider, "verify_token", verify)
    browsing = Mock(wraps=filesystem.services.browsing)
    monkeypatch.setattr(filesystem.services, "browsing", browsing)
    server = FastMCP(auth=provider)
    callers = CurrentFilesystemCallerCapture(server, StaticFilesystemGroupClaimFields("groups"))
    visibility = FilesystemToolVisibility(callers, filesystem.runtime)
    server.add_middleware(FilesystemVisibilityMiddleware(visibility))
    register_filesystem_tools(
        McpObservedToolRegistrar(server, Mock(spec=McpInvocationPublisher)),
        callers, filesystem.services, visibility, filesystem.approval,
    )
    app = server.http_app(stateless_http=True)
    async with app.router.lifespan_context(app):
        async with Client(http_transport(app)) as client:
            names = {tool.name for tool in await client.list_tools()}
            result = await client.call_tool("get_filesystem_node", {"node_id": str(home.id)}, raise_on_error=False)
    assert ("get_filesystem_node" in names) is visible
    assert result.is_error is not visible
    assert verify.await_count > 0
    if visible:
        browsing.assert_called_once_with()
    else:
        browsing.assert_not_called()
        assert "Unknown tool" in result.content[0].text


async def listed_templates(filesystem: FilesystemMcp) -> set[str]:
    async with Client(filesystem.server) as client:
        return {str(template.uri_template) for template in await client.list_resource_templates()}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
async def test_resource_template_requires_accessible_file(filesystem_mcp: FilesystemMcp, kind: str) -> None:
    await private_node(filesystem_mcp, kind)
    await filesystem_mcp.runtime.reconcile()
    assert await listed_templates(filesystem_mcp) == ({FILE_RESOURCE_TEMPLATE} if kind == "file" else set())
    select_caller(filesystem_mcp, "bob")
    assert await listed_templates(filesystem_mcp) == set()


@pytest.mark.asyncio
async def test_template_discovery_is_root_scoped_without_database_or_service_access(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    await private_node(filesystem_mcp)
    await filesystem_mcp.runtime.reconcile()
    forbidden = Mock(side_effect=AssertionError("Discovery performed I/O"))
    monkeypatch.setattr(filesystem_mcp.database, "read_session", forbidden)
    monkeypatch.setattr(filesystem_mcp.services, "content", forbidden)
    assert await listed_templates(filesystem_mcp) == {FILE_RESOURCE_TEMPLATE}
    token = _REQUEST_CONNECTOR_SCOPE.set("connector")
    try:
        assert await listed_templates(filesystem_mcp) == set()
    finally:
        _REQUEST_CONNECTOR_SCOPE.reset(token)
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_failed_runtime_hydration_keeps_only_home_discovery(filesystem_mcp: FilesystemMcp) -> None:
    reader = Mock(spec=FilesystemAuthorizationReader)
    reader.read = AsyncMock(side_effect=RuntimeError("unavailable"))
    runtime = FilesystemDiscoveryRuntime(reader)
    with pytest.raises(RuntimeError):
        await runtime.reconcile()
    assert await FilesystemToolVisibility(filesystem_mcp.callers, runtime).capture() == frozenset({FilesystemOperation.HOME})


@pytest.mark.asyncio
async def test_template_discovery_preserves_unrelated_template(filesystem_mcp: FilesystemMcp) -> None:
    @filesystem_mcp.server.resource("other://values/{value}")
    def unrelated(value: str) -> str:
        return value

    select_caller(filesystem_mcp, "bob")
    assert await listed_templates(filesystem_mcp) == {"other://values/{value}"}


async def grant(
    filesystem: FilesystemMcp, node_id: UUID, subject: str, permissions: set[Permission],
    principal_type: PrincipalType = PrincipalType.USER,
) -> None:
    await create_access_control_driver(database=filesystem.database).add_grant(AccessGrant(
        node_id=node_id,
        principal=Principal(type=principal_type, issuer="https://issuer", id=subject),
        permissions=permissions, recursive=False,
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,expected", [
    ("file", FILE_READ_TOOLS),
    ("directory", INSPECT_TOOLS | {"list_filesystem_children"}),
])
async def test_direct_node_grants_respect_kind_without_root_access(
    filesystem_mcp: FilesystemMcp, kind: str, expected: set[str],
) -> None:
    node_id = await private_node(filesystem_mcp, kind)
    await grant(filesystem_mcp, node_id, "bob", {Permission.DISCOVER, Permission.READ})
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob")
    assert await listed_tools(filesystem_mcp) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("same_node", [True, False])
async def test_permissions_from_groups_combine_only_on_same_node(
    filesystem_mcp: FilesystemMcp, same_node: bool,
) -> None:
    first = await private_node(filesystem_mcp)
    second = first if same_node else await private_node(filesystem_mcp)
    await grant(filesystem_mcp, first, "discoverers", {Permission.DISCOVER}, PrincipalType.GROUP)
    await grant(filesystem_mcp, second, "readers", {Permission.READ}, PrincipalType.GROUP)
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob", ("discoverers", "readers"))
    assert await listed_tools(filesystem_mcp) == (FILE_READ_TOOLS if same_node else INSPECT_TOOLS)


@pytest.mark.asyncio
async def test_file_only_discover_permission_exposes_browse_stat(filesystem_mcp: FilesystemMcp) -> None:
    node_id = await private_node(filesystem_mcp)
    await grant(filesystem_mcp, node_id, "bob", {Permission.DISCOVER})
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob")
    assert await listed_tools(filesystem_mcp) == INSPECT_TOOLS
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": str(node_id)},
        })
    assert result.structured_content["result"]["node"]["id"] == str(node_id)


@pytest.mark.asyncio
async def test_revoked_last_witness_rejects_retained_invocation_before_discovery_refresh(
    filesystem_mcp: FilesystemMcp,
) -> None:
    node_id = await private_node(filesystem_mcp)
    await grant(filesystem_mcp, node_id, "bob", {Permission.DISCOVER, Permission.READ})
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob")
    assert await listed_tools(filesystem_mcp) == FILE_READ_TOOLS
    await create_access_control_driver(database=filesystem_mcp.database).remove_grant(
        node_id, Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
    )
    assert await listed_tools(filesystem_mcp) == FILE_READ_TOOLS
    async with Client(filesystem_mcp.server) as client:
        with pytest.raises(MCPError, match="filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask an administrator for namespace access."):
            await client.read_resource(file_resource_uri(node_id))
    await filesystem_mcp.runtime.reconcile()
    assert await listed_tools(filesystem_mcp) == {"filesystem_browse"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,permissions,visible", [
    ("file", {Permission.DISCOVER, Permission.READ}, True),
    ("file", {Permission.DISCOVER}, False),
    ("file", {Permission.READ}, False),
    ("directory", {Permission.DISCOVER, Permission.READ}, False),
])
async def test_template_visibility_requires_in_memory_file_read_witness(
    filesystem_mcp: FilesystemMcp, kind: str, permissions: set[Permission], visible: bool,
) -> None:
    node_id = await private_node(filesystem_mcp, kind)
    await grant(filesystem_mcp, node_id, "bob", permissions)
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob")
    assert (FILE_RESOURCE_TEMPLATE in await listed_templates(filesystem_mcp)) is visible



@pytest.mark.asyncio
async def test_old_namespace_root_grants_do_not_leak_descendant_access_or_tool_discovery(
    filesystem_mcp: FilesystemMcp, filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    filesystem = filesystem_invocation_mcp
    async with Client(filesystem.server) as client:
        parent = await root_id(client)
        child = await create_node(client, parent, "private-file", "file")
        await create_access_control_driver(database=filesystem.database).add_grant(AccessGrant(
            node_id=UUID(parent), principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
            permissions=set(Permission), recursive=True,
        ))
        select_caller(filesystem, "bob")
        for node_id in (parent, child):
            denied = await client.call_tool("get_filesystem_node", {"node_id": node_id}, raise_on_error=False)
            assert denied.is_error
        with pytest.raises(MCPError, match="filesystem_permission_denied"):
            await client.read_resource(file_resource_uri(UUID(child)))
    await filesystem.runtime.reconcile()
    assert await listed_tools(filesystem_mcp) == {"filesystem_browse"}
    assert await listed_templates(filesystem_mcp) == set()
