import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from jsonschema import validate

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.sharing import FilesystemSharing, SharingRecipientSearchQuery, SharingRecipientSearchResult, SharingScope
from umbod.core.groups import RegisterGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.store import DatabaseIdentityDirectory, SessionObservedUsers
from umbod.infrastructure import create_access_control_driver

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_sharing_tools import DENIED, LIST
from .test_tools import root_id


@pytest.mark.asyncio
@pytest.mark.parametrize("patch", [
    {"query": ""}, {"query": " \n "}, {"query": "a" * 201}, {"query": None},
    {"query": 1}, {"query": True}, {"query": []}, {"node_id": 1},
    {"recipient_type": None}, {"recipient_type": ""}, {"recipient_type": "both"},
    {"recipient_type": ["group"]}, {"recipient_type": True},
    *[{field: "SECRET"} for field in ("issuer", "subject", "limit", "offset", "unknown")],
])
async def test_invalid_search_never_captures_or_constructs_service(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, patch: dict[str, Any],
) -> None:
    factory = Mock()
    monkeypatch.setattr(filesystem_invocation_mcp.services, "sharing", factory)
    captures = filesystem_invocation_mcp.callers.count
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(LIST, {"node_id": str(uuid4()), "query": "name", **patch}, raise_on_error=False)
    assert result.content[0].text == "filesystem_invalid_sharing: Invalid filesystem sharing arguments"
    assert result.structured_content is None
    assert filesystem_invocation_mcp.callers.count == captures
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,types", [
    ({}, frozenset({"group", "user"})),
    ({"recipient_type": "group"}, frozenset({"group"})),
    ({"recipient_type": "user"}, frozenset({"user"})),
])
async def test_boundary_normalizes_scope_and_query(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
    scope: dict[str, str], types: frozenset[str],
) -> None:
    service = Mock(spec=FilesystemSharing)
    service.search_recipients = AsyncMock(return_value=SharingRecipientSearchResult(recipients=(), has_more=False))
    factory = Mock(return_value=service)
    monkeypatch.setattr(filesystem_invocation_mcp.services, "sharing", factory)
    node_id = uuid4()
    async with Client(filesystem_invocation_mcp.server) as client:
        await client.call_tool(LIST, {"node_id": str(node_id), "query": "  Name  ", **scope})
    service.search_recipients.assert_awaited_once_with(
        filesystem_invocation_mcp.callers.current.get(), node_id,
        SharingRecipientSearchQuery(query="Name", scope=SharingScope(recipient_types=types)),
    )
    factory.assert_called_once_with()


@pytest.mark.asyncio
async def test_listing_does_not_open_database_sessions_or_capture_callers(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = Mock(side_effect=AssertionError("unexpected read"))
    write = Mock(side_effect=AssertionError("unexpected write"))
    monkeypatch.setattr(filesystem_invocation_mcp.database, "read_session", read)
    monkeypatch.setattr(filesystem_invocation_mcp.database, "session", write)
    captures = filesystem_invocation_mcp.callers.count
    async with Client(filesystem_invocation_mcp.server) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert LIST in names
    assert not {"search_users", "filesystem_list_sharing_groups"} & names
    assert filesystem_invocation_mcp.callers.count == captures
    read.assert_not_called()
    write.assert_not_called()


async def observe(directory: DatabaseIdentityDirectory, issuer: str, subject: str, name: str) -> None:
    await directory.observe(IdentityObservation(
        issuer=issuer, subject=subject, claim="groups", groups=("private-membership",), name=name,
        email="private@example.com", email_verification="verified", observed_at=datetime.now(timezone.utc),
    ))


@pytest.mark.asyncio
async def test_node_authorized_search_projects_only_typed_public_labels_and_identifiers(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    directory = DatabaseIdentityDirectory(filesystem_invocation_mcp.database)
    await observe(directory, "https://issuer", "private-subject-one", "Observed   Person")
    await observe(directory, "https://issuer", "private-subject-two", "Observed   Person")
    await observe(directory, "https://foreign", "private-foreign-subject", "Observed Person")
    await observe(directory, "https://issuer", "private-unnamed-subject", "")
    groups = create_group_management(database=filesystem_invocation_mcp.database)
    await groups.register_group_metadata(RegisterGroupMetadata(
        group_id="exact-group-id", label="Observed Group", description="private-description",
    ))
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        result = await client.call_tool(LIST, {"node_id": node_id, "query": "  OBSERVED  "})
        descriptor = next(tool for tool in await client.list_tools() if tool.name == LIST)
        for query in ("private@example.com", "private-subject-one", "private-unnamed-subject"):
            empty = await client.call_tool(LIST, {"node_id": node_id, "query": query})
            assert empty.structured_content == {"recipients": [], "has_more": False}
    payload = result.structured_content
    assert payload["has_more"] is False
    assert payload["recipients"][0] == {"type": "group", "group_id": "exact-group-id", "label": "Observed Group"}
    users = payload["recipients"][1:]
    assert len(users) == 2
    assert len({user["user_id"] for user in users}) == 2
    assert all(set(user) == {"type", "user_id", "label"} and user["type"] == "user" for user in users)
    assert all(user["label"] == "Observed   Person" for user in users)
    assert json.loads(result.content[0].text) == payload
    validate(payload, descriptor.output_schema)
    assert "private" not in result.content[0].text
    assert "https://" not in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance,issuer,subject", [
    (AuthenticationProvenance.LOCAL_TEST, "https://issuer", "alice"),
    (AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED, "https://issuer", "alice"),
    (AuthenticationProvenance.LOCAL_SIMULATION, "https://issuer", "alice"),
    (AuthenticationProvenance.LOCAL_SEMANTIC, "https://issuer", "alice"),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, "https://foreign", "foreign-authorized"),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, "", "alice"),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, "https://issuer", ""),
])
async def test_directory_authentication_rejects_unverified_or_foreign_callers_before_user_reads(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
    provenance: AuthenticationProvenance, issuer: str, subject: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
    if issuer and subject:
        await create_access_control_driver(database=filesystem_invocation_mcp.database).add_grant(AccessGrant(
            node_id=UUID(node_id), principal=Principal(type=PrincipalType.USER, issuer=issuer, id=subject),
            permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
        ))
    search = AsyncMock(side_effect=AssertionError("private directory must not be read"))
    monkeypatch.setattr(SessionObservedUsers, "search_user_names", search)
    filesystem_invocation_mcp.callers.current.set(caller_snapshot(subject, issuer, (), provenance))
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(LIST, {"node_id": node_id, "query": "Observed"}, raise_on_error=False)
    assert result.content[0].text == DENIED
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_only_search_does_not_require_configured_issuer_directory_authority(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
    await create_access_control_driver(database=filesystem_invocation_mcp.database).add_grant(AccessGrant(
        node_id=UUID(node_id), principal=Principal(type=PrincipalType.USER, issuer="https://foreign", id="foreign"),
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
    ))
    search = AsyncMock(side_effect=AssertionError("unexpected directory lookup"))
    monkeypatch.setattr(SessionObservedUsers, "search_user_names", search)
    filesystem_invocation_mcp.callers.current.set(caller_snapshot(
        "foreign", "https://foreign", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
    ))
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(LIST, {"node_id": node_id, "query": "writers", "recipient_type": "group"})
    assert result.structured_content["has_more"] is False
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_retained_tool_rechecks_current_identity_before_directory_reads(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        first = await client.call_tool(LIST, {"node_id": node_id, "query": "Observed"})
        assert not first.is_error
        search = AsyncMock(side_effect=AssertionError("stale caller directory lookup"))
        monkeypatch.setattr(SessionObservedUsers, "search_user_names", search)
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "alice", "https://issuer", ("writers",), AuthenticationProvenance.LOCAL_TEST,
        ))
        denied = await client.call_tool(LIST, {"node_id": node_id, "query": "Observed"}, raise_on_error=False)
    assert denied.content[0].text == DENIED
    search.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.SHARE}])
async def test_both_node_permissions_precede_directory_lookup(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, permissions: set[Permission],
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
    if permissions:
        await create_access_control_driver(database=filesystem_invocation_mcp.database).add_grant(AccessGrant(
            node_id=UUID(node_id), principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
            permissions=permissions, recursive=False,
        ))
    search = AsyncMock(side_effect=AssertionError("directory lookup before node authority"))
    monkeypatch.setattr(SessionObservedUsers, "search_user_names", search)
    filesystem_invocation_mcp.callers.current.set(caller_snapshot(
        "bob", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
    ))
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(LIST, {"node_id": node_id, "query": "Observed"}, raise_on_error=False)
    assert result.content[0].text == DENIED
    search.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("count,has_more", [(50, False), (51, True)])
async def test_global_limit_is_fifty_eligible_recipients_with_group_first_ordering(
    filesystem_invocation_mcp: FilesystemMcp, count: int, has_more: bool,
) -> None:
    groups = create_group_management(database=filesystem_invocation_mcp.database)
    for index in reversed(range(count - 1)):
        await groups.register_group_metadata(RegisterGroupMetadata(
            group_id=f"group-{index:03}", label=f"Match {index:03}", description="",
        ))
    await observe(DatabaseIdentityDirectory(filesystem_invocation_mcp.database), "https://issuer", "subject", "Match 000")
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        result = await client.call_tool(LIST, {"node_id": node_id, "query": "match"})
    payload = result.structured_content
    assert payload["has_more"] is has_more
    recipients = payload["recipients"]
    assert len(recipients) == 50
    assert [recipient["group_id"] for recipient in recipients if recipient["type"] == "group"] == [
        f"group-{index:03}" for index in range(count - 1)
    ]
    assert recipients[-1]["type"] == ("group" if has_more else "user")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["search_users", "filesystem_list_sharing_groups"])
async def test_removed_tool_names_cannot_be_invoked(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, name: str,
) -> None:
    factory = Mock()
    monkeypatch.setattr(filesystem_invocation_mcp.services, "sharing", factory)
    captures = filesystem_invocation_mcp.callers.count
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(name, {"node_id": str(uuid4()), "query": "Observed"}, raise_on_error=False)
    assert result.is_error
    assert filesystem_invocation_mcp.callers.count == captures
    factory.assert_not_called()
