import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx2
import pytest
from fastmcp import Client, FastMCP
from mcp.shared.exceptions import MCPError
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from starlette.applications import Starlette

from umbod.core.callers import AuthenticationProvenance, CallerContext, CallerSnapshot, GroupMembership, UnavailableSubject
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization.discovery import AuthorizationGrant, AuthorizationNode, FilesystemAuthorizationSnapshot
from umbod.core.filesystem.models import NodeKind, Ownership
from umbod.infrastructure import create_access_control_driver
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, StaticFilesystemGroupClaimFields, register_filesystem_tools
from umbod.mcp.filesystem.authorization import FilesystemToolVisibility, FilesystemVisibilityMiddleware
from umbod.mcp.filesystem.runtime import FilesystemDiscoveryRuntime
from umbod.mcp.filesystem.links import FILE_RESOURCE_TEMPLATE, file_resource_uri
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.tools import McpObservedToolRegistrar

from .conftest import FilesystemMcp, ScopedCallerCapture, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id

BOOTSTRAP_TOOLS = {
    "filesystem_browse", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
    "create_filesystem_file", "create_filesystem_directory", "filesystem_upload", "update_filesystem_node",
}
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
async def test_bootstrap_writer_sees_only_operations_with_root_witness(filesystem_mcp: FilesystemMcp) -> None:
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [(), ("administrators",)])
async def test_no_filesystem_permission_hides_tools_even_for_administrator_group(
    filesystem_mcp: FilesystemMcp, groups: tuple[str, ...],
) -> None:
    select_caller(filesystem_mcp, "bob", groups)
    assert await listed_tools(filesystem_mcp) == set()


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
async def test_owned_file_without_root_exposes_file_operations_not_directory_operations(
    filesystem_mcp: FilesystemMcp,
) -> None:
    await private_node(filesystem_mcp)
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "alice")
    assert await listed_tools(filesystem_mcp) == FILE_READ_TOOLS | {
        "filesystem_delete_file", "filesystem_share", "filesystem_search_sharing_recipients", "update_filesystem_node",
    }


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
@pytest.mark.parametrize("issuer,provenance", [
    ("https://other-issuer", AuthenticationProvenance.UPSTREAM_VERIFIED),
    ("https://issuer", AuthenticationProvenance.LOCAL_TEST),
    ("https://issuer", AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    ("https://issuer", AuthenticationProvenance.UNAVAILABLE),
])
async def test_unverified_or_wrong_issuer_cannot_discover_filesystem_tools(
    filesystem_mcp: FilesystemMcp, issuer: str, provenance: AuthenticationProvenance,
) -> None:
    snapshot = CallerSnapshot(
        caller=CallerContext(authentication=provenance, subject=UnavailableSubject(kind="unavailable")),
        groups=GroupMembership(group_ids=("writers",)),
    ) if provenance == AuthenticationProvenance.UNAVAILABLE else caller_snapshot("alice", issuer, ("writers",), provenance)
    filesystem_mcp.callers.current.set(snapshot)
    assert await listed_tools(filesystem_mcp) == set()


@pytest.mark.asyncio
async def test_concurrent_discovery_does_not_share_callers(filesystem_mcp: FilesystemMcp) -> None:
    async def discover(subject: str, groups: tuple[str, ...]) -> set[str]:
        select_caller(filesystem_mcp, subject, groups)
        return await listed_tools(filesystem_mcp)

    assert await asyncio.gather(discover("alice", ("writers",)), discover("bob", ())) == [
        BOOTSTRAP_TOOLS, set(),
    ]


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
    forbidden = Mock(side_effect=AssertionError("Discovery performed I/O or service construction"))
    monkeypatch.setattr(filesystem_mcp.database, "read_session", forbidden)
    for method in ("browsing", "creation", "content", "deletion", "updates", "sharing", "uploads"):
        monkeypatch.setattr(filesystem_mcp.services, method, forbidden)
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS
    assert await listed_tools(filesystem_mcp) == BOOTSTRAP_TOOLS
    forbidden.assert_not_called()


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
        with pytest.raises(MCPError, match="filesystem_permission_denied: Filesystem access denied"):
            await client.read_resource(file_resource_uri(node_id))
    await filesystem_mcp.runtime.reconcile()
    assert await listed_tools(filesystem_mcp) == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("owned,present", [(False, True), (True, False)])
async def test_absent_or_unowned_nodes_cannot_supply_visibility_witness(owned: bool, present: bool) -> None:
    node_id = uuid4()
    callers = ScopedCallerCapture()
    callers.current.set(caller_snapshot("alice", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED))
    reader = Mock()
    reader.read = AsyncMock(return_value=FilesystemAuthorizationSnapshot(
        nodes=(AuthorizationNode(node_id=node_id, kind=NodeKind.FILE),) if present else (),
        ownerships=(Ownership(node_id=node_id, owner=Principal(
            type=PrincipalType.USER, issuer="https://issuer", id="alice",
        )),) if owned else (), grants=(AuthorizationGrant(
            node_id=node_id, principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="alice"),
            permissions=frozenset({Permission.DISCOVER, Permission.READ}), recursive=False,
        ),),
    ))
    runtime = FilesystemDiscoveryRuntime(reader)
    await runtime.reconcile()
    assert await FilesystemToolVisibility(callers, runtime).capture() == frozenset()


def http_transport(app: Starlette) -> StreamableHttpTransport:
    transport = httpx2.ASGITransport(app=app)

    def create_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=transport, **kwargs)

    return StreamableHttpTransport(
        "http://localhost/mcp", headers={"Authorization": "Bearer accepted"}, httpx_client_factory=create_client,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("groups,visible", [([], False), (["writers"], True)])
async def test_http_lookup_enforces_visibility_callback_with_verified_request_identity(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, groups: list[str], visible: bool,
) -> None:
    provider = GoogleProvider(
        client_id="client", client_secret="secret", base_url="http://localhost",
        jwt_signing_key="filesystem-test-signing-key",
    )
    verify = AsyncMock(return_value=AccessToken(
        token="accepted", client_id="client", scopes=provider.required_scopes,
        claims={"iss": "https://issuer", "sub": "alice", "groups": groups},
    ))
    monkeypatch.setattr(provider, "verify_token", verify)
    browsing = Mock(wraps=filesystem_mcp.services.browsing)
    monkeypatch.setattr(filesystem_mcp.services, "browsing", browsing)
    server = FastMCP(auth=provider)
    callers = CurrentFilesystemCallerCapture(server, StaticFilesystemGroupClaimFields("groups"))
    visibility = FilesystemToolVisibility(callers, filesystem_mcp.runtime)
    server.add_middleware(FilesystemVisibilityMiddleware(visibility))
    register_filesystem_tools(
        McpObservedToolRegistrar(server, Mock(spec=McpInvocationPublisher)),
        callers, filesystem_mcp.services, visibility, filesystem_mcp.approval,
    )
    app = server.http_app(stateless_http=True)
    async with app.router.lifespan_context(app):
        async with Client(http_transport(app)) as client:
            names = {tool.name for tool in await client.list_tools()}
            result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert ("get_filesystem_root" in names) is visible
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
async def test_template_discovery_is_root_only_and_does_not_construct_services(
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
async def test_template_discovery_preserves_unrelated_template(
    filesystem_mcp: FilesystemMcp,
) -> None:
    @filesystem_mcp.server.resource("other://values/{value}")
    def unrelated(value: str) -> str:
        return value

    select_caller(filesystem_mcp, "bob")
    assert await listed_templates(filesystem_mcp) == {"other://values/{value}"}
