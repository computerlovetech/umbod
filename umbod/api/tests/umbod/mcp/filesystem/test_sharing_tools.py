import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from jsonschema import validate

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.sharing import (
    EligibleSharingGroups, FilesystemSharing, GroupPolicy, InvalidSharingPolicy,
    ShareNodeGroupResult, SharingPolicyUnavailable,
)
from umbod.core.groups import RegisterGroupMetadata, UpdateGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.infrastructure import create_access_control_driver
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.filesystem.sharing_tools import FilesystemListSharingGroupsTool, FilesystemShareTool
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id

LIST = "filesystem_list_sharing_groups"
SHARE = "filesystem_share"
DENIED = "filesystem_permission_denied: Filesystem access denied"


def arguments(tool: str, node_id: str) -> dict[str, Any]:
    return {"node_id": node_id, **({"group_id": "writers", "permissions": ["read"]} if tool == SHARE else {})}


@pytest.mark.asyncio
async def test_advertised_schemas_and_annotations_are_exact(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        descriptors = {tool.name: tool for tool in await client.list_tools()}
    for name in (LIST, SHARE):
        descriptor = descriptors[name]
        schema = descriptor.input_schema
        required = {"node_id", "group_id", "permissions"} if name == SHARE else {"node_id"}
        assert set(schema["properties"]) == set(schema["required"]) == required
        assert schema["additionalProperties"] is False
        assert schema["properties"]["node_id"]["format"] == "uuid"
        assert descriptor.annotations.read_only_hint == (name == LIST)
        assert descriptor.annotations.destructive_hint is False
        assert descriptor.annotations.idempotent_hint is True
        assert descriptor.annotations.open_world_hint is False
    share = descriptors[SHARE]
    assert share.input_schema["properties"]["permissions"]["minItems"] == 1
    assert set(share.input_schema["properties"]["permissions"]["items"]["enum"]) == {"discover", "read", "write", "delete", "share"}
    assert set(share.output_schema["properties"]) == set(share.output_schema["required"]) == {
        "node_id", "group_id", "permissions", "changed",
    }
    assert share.output_schema["properties"]["permissions"]["minItems"] == 1
    listing = descriptors[LIST].output_schema
    assert set(listing["properties"]) == set(listing["required"]) == {"groups"}
    assert listing["additionalProperties"] is False
    group = listing["properties"]["groups"]["items"]
    assert set(group["properties"]) == set(group["required"]) == {"group_id", "label", "description"}
    assert group["additionalProperties"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
async def test_additive_union_retry_preserves_other_grants_and_exact_ids(
    filesystem_mcp: FilesystemMcp, kind: str,
) -> None:
    group_id = ' Team/"\n '
    groups = create_group_management(database=filesystem_mcp.database)
    await groups.register_group_metadata(RegisterGroupMetadata(group_id=group_id, label="Team", description="Registered"))
    policies = create_access_control_driver(database=filesystem_mcp.database)
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "shared", kind)
        protected = AccessGrant(
            node_id=UUID(node_id), principal=Principal(type=PrincipalType.USER, issuer="foreign", id="protected"),
            permissions={Permission.DELETE}, recursive=False,
        )
        other = AccessGrant(
            node_id=UUID(node_id), principal=Principal(type=PrincipalType.GROUP, issuer="https://issuer", id="writers"),
            permissions={Permission.WRITE}, recursive=False,
        )
        child = await create_node(client, node_id, "private-child", "file") if kind == "directory" else None
        await policies.add_grant(protected)
        await policies.add_grant(other)
        first = await client.call_tool(SHARE, {"node_id": node_id, "group_id": group_id, "permissions": ["read"]})
        second = await client.call_tool(SHARE, {"node_id": node_id, "group_id": group_id, "permissions": ["discover"]})
        retry = await client.call_tool(SHARE, {"node_id": node_id, "group_id": group_id, "permissions": ["discover"]})
        descriptor = next(tool for tool in await client.list_tools() if tool.name == SHARE)
    assert first.structured_content == {"node_id": node_id, "group_id": group_id, "permissions": ["read"], "changed": True}
    assert second.structured_content == {"node_id": node_id, "group_id": group_id, "permissions": ["discover", "read"], "changed": True}
    assert retry.structured_content == {**second.structured_content, "changed": False}
    for result in (first, second, retry):
        validate(result.structured_content, descriptor.output_schema)
        assert json.loads(result.content[0].text) == result.structured_content
        assert json.dumps(group_id) in result.content[0].text
    grants = await policies.list_grants(UUID(node_id))
    assert protected in grants
    assert other in grants
    if child is not None:
        assert not await policies.list_grants(UUID(child))
    assert any(sample.labels["tool_name"] == SHARE and sample.labels["outcome"] == "success"
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
async def test_eligible_groups_use_current_metadata_and_exclude_protected_collisions(filesystem_mcp: FilesystemMcp) -> None:
    groups = create_group_management(database=filesystem_mcp.database)
    group_id = ' Exact/"\n '
    label = 'Current "label"\nnext'
    await groups.register_group_metadata(RegisterGroupMetadata(group_id=group_id, label="Old", description="Old"))
    await groups.update_group_metadata(group_id, UpdateGroupMetadata(label=label, description="Current", expected_revision=1))
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "owned", "file")
        await create_access_control_driver(database=filesystem_mcp.database).add_grant(AccessGrant(
            node_id=UUID(node_id), principal=Principal(type=PrincipalType.GROUP, issuer="https://issuer", id="writers"),
            permissions={Permission.READ}, recursive=True,
        ))
        result = await client.call_tool(LIST, {"node_id": node_id})
        descriptor = next(tool for tool in await client.list_tools() if tool.name == LIST)
        blocked = await client.call_tool(SHARE, arguments(SHARE, node_id), raise_on_error=False)
        unknown = await client.call_tool(SHARE, {"node_id": node_id, "group_id": "unregistered", "permissions": ["read"]}, raise_on_error=False)
    assert result.structured_content == {"groups": [{"group_id": group_id, "label": label, "description": "Current"}]}
    validate(result.structured_content, descriptor.output_schema)
    assert json.loads(result.content[0].text) == result.structured_content
    assert json.dumps(label) in result.content[0].text
    for failure in (blocked, unknown):
        assert failure.content[0].text == "filesystem_invalid_sharing_policy: Invalid filesystem sharing policy"
        assert failure.structured_content is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [LIST, SHARE])
@pytest.mark.parametrize("patch", [
    {"node_id": "invalid"}, {"node_id": None},
    *[{field: "SECRET"} for field in ("caller", "owner", "issuer", "recursive", "revision", "principal")],
])
async def test_invalid_arguments_rejected_before_caller_capture(
    filesystem_mcp: FilesystemMcp, tool: str, patch: dict[str, Any],
) -> None:
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool(tool, {**arguments(tool, str(uuid4())), **patch}, raise_on_error=False)
    assert result.content[0].text == "filesystem_invalid_sharing: Invalid filesystem sharing arguments"
    assert result.structured_content is None
    assert filesystem_mcp.callers.count == captures


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {}, {"node_id": str(uuid4())},
    *[{"node_id": str(uuid4()), "group_id": value, "permissions": ["read"]} for value in ("", " \n", None, 1)],
    *[{"node_id": str(uuid4()), "group_id": "writers", "permissions": value}
      for value in ([], ["READ"], ["unknown"], [None], [True], "read", None)],
])
async def test_share_requires_explicit_nonempty_valid_permissions_and_group(
    filesystem_mcp: FilesystemMcp, payload: dict[str, Any],
) -> None:
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool(SHARE, payload, raise_on_error=False)
    assert result.content[0].text == "filesystem_invalid_sharing: Invalid filesystem sharing arguments"
    assert filesystem_mcp.callers.count == captures


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [LIST, SHARE])
@pytest.mark.parametrize("provenance,subject,issuer,memberships", [
    (AuthenticationProvenance.LOCAL_TEST, "alice", "https://issuer", ("writers",)),
    (AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED, "alice", "https://issuer", ("writers",)),
    (AuthenticationProvenance.LOCAL_SIMULATION, "alice", "https://issuer", ("writers",)),
    (AuthenticationProvenance.LOCAL_SEMANTIC, "alice", "https://issuer", ("writers",)),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, "alice", "foreign", ("writers",)),
    (AuthenticationProvenance.UPSTREAM_VERIFIED, "admin", "https://issuer", ("umbod-admins", "writers")),
])
async def test_missing_and_private_nodes_are_indistinguishable_without_direct_authority(
    filesystem_mcp: FilesystemMcp, tool: str, provenance: AuthenticationProvenance,
    subject: str, issuer: str, memberships: tuple[str, ...],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        filesystem_mcp.callers.current.set(caller_snapshot(subject, issuer, memberships, provenance))
        private = await client.call_tool(tool, arguments(tool, node_id), raise_on_error=False)
        missing = await client.call_tool(tool, arguments(tool, str(uuid4())), raise_on_error=False)
    assert private.content == missing.content
    assert private.content[0].text == DENIED


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [LIST, SHARE])
async def test_discovery_has_no_io_and_each_invocation_captures_and_calls_once(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, tool: str,
) -> None:
    snapshot = filesystem_mcp.callers.current.get()
    node_id = uuid4()
    service = Mock(spec=FilesystemSharing)
    service.eligible_groups = AsyncMock(return_value=EligibleSharingGroups(groups=()))
    service.share = AsyncMock(return_value=ShareNodeGroupResult(
        node_id=node_id, group_id="writers", permissions={Permission.READ}, changed=True,
    ))
    factory = Mock(return_value=service)
    monkeypatch.setattr(filesystem_mcp.services, "sharing", factory)
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        await client.list_tools()
        assert factory.call_count == 0
        assert filesystem_mcp.callers.count == captures
        for _ in range(2):
            await client.call_tool(tool, arguments(tool, str(node_id)))
    assert filesystem_mcp.callers.count == captures + 2
    assert factory.call_count == 2
    if tool == LIST:
        assert service.eligible_groups.await_count == 2
        service.eligible_groups.assert_awaited_with(snapshot, node_id)
        service.share.assert_not_awaited()
    else:
        assert service.share.await_count == 2
        service.share.assert_awaited_with(snapshot, node_id, GroupPolicy(group_id="writers", permissions={Permission.READ}))
        service.eligible_groups.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [LIST, SHARE])
@pytest.mark.parametrize("error_type,expected", [
    (InvalidSharingPolicy, "filesystem_invalid_sharing_policy: Invalid filesystem sharing policy"),
    (SharingPolicyUnavailable, "filesystem_policy_unavailable: Filesystem sharing configuration unavailable"),
    (RuntimeError, "filesystem_operation_failed: Filesystem operation failed"),
])
async def test_failures_are_sanitized_and_observed(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
    tool: str, error_type: type[Exception], expected: str,
) -> None:
    service = Mock(spec=FilesystemSharing)
    setattr(service, "share" if tool == SHARE else "eligible_groups", AsyncMock(side_effect=error_type("SECRET /private")))
    monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: service)
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool(tool, arguments(tool, str(uuid4())), raise_on_error=False)
    assert result.content[0].text == expected
    assert result.structured_content is None
    assert any(sample.labels["tool_name"] == tool and sample.labels["outcome"] == "failure"
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [LIST, SHARE])
async def test_connector_scope_excludes_sharing_before_capture(filesystem_mcp: FilesystemMcp, tool: str) -> None:
    captures = filesystem_mcp.callers.count
    token = set_request_connector_scope("connector-only")
    try:
        async with Client(filesystem_mcp.server) as client:
            descriptors = await client.list_tools()
            result = await client.call_tool(tool, arguments(tool, str(uuid4())), raise_on_error=False)
        assert tool not in {descriptor.name for descriptor in descriptors}
        assert result.is_error
        assert filesystem_mcp.callers.count == captures
    finally:
        reset_request_connector_scope(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [LIST, SHARE])
async def test_direct_authority_is_fresh_and_concurrent_callers_are_isolated(
    filesystem_mcp: FilesystemMcp, tool: str,
) -> None:
    policies = create_access_control_driver(database=filesystem_mcp.database)
    principal = Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob")
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
    await policies.add_grant(AccessGrant(
        node_id=UUID(node_id), principal=principal,
        permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
    ))

    async def invoke(subject: str) -> bool:
        filesystem_mcp.callers.current.set(caller_snapshot(
            subject, "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        async with Client(filesystem_mcp.server) as client:
            result = await client.call_tool(tool, arguments(tool, node_id), raise_on_error=False)
        return result.is_error

    assert await asyncio.gather(invoke("bob"), invoke("charlie")) == [False, True]
    await policies.remove_grant(UUID(node_id), principal)
    assert await invoke("bob") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_type", [FilesystemListSharingGroupsTool, FilesystemShareTool])
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
async def test_cancellation_propagates(
    filesystem_mcp: FilesystemMcp, tool_type: type[FilesystemListSharingGroupsTool | FilesystemShareTool], stage: str,
) -> None:
    callers = Mock(spec=FilesystemCallerCapture)
    callers.capture.return_value = filesystem_mcp.callers.current.get()
    service = Mock(spec=FilesystemSharing)
    service.eligible_groups = AsyncMock(side_effect=asyncio.CancelledError())
    service.share = AsyncMock(side_effect=asyncio.CancelledError())
    factory = Mock(spec=FilesystemServiceFactory)
    factory.sharing.return_value = service
    if stage == "capture":
        callers.capture.side_effect = asyncio.CancelledError()
    elif stage == "factory":
        factory.sharing.side_effect = asyncio.CancelledError()
    tool = tool_type(callers, factory)
    with pytest.raises(asyncio.CancelledError):
        await tool.run(arguments(tool.name, str(uuid4())))
