import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from jsonschema import ValidationError as SchemaValidationError, validate

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.sharing import (
    FilesystemSharing, GroupSharingTarget, InvalidSharingPolicy,
    SharingRecipientSearchQuery, SharingRecipientSearchResult, SharingScope,
    ShareNodePolicy, ShareNodeResult, SharingPolicyUnavailable, UserSharingTarget,
)
from umbod.core.groups import RegisterGroupMetadata, UpdateGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.core.identity_directory.user_models import ScopedUserSearch
from umbod.infrastructure import create_access_control_driver
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.filesystem.sharing_tools import FilesystemSearchSharingRecipientsTool, FilesystemShareTool
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id

LIST = "filesystem_search_sharing_recipients"
SHARE = "filesystem_share"
DENIED = "filesystem_permission_denied: Filesystem access denied"


def arguments(tool: str, node_id: str) -> dict[str, Any]:
    return {"node_id": node_id, **({"group_id": "writers", "permissions": ["read"]} if tool == SHARE else {"query": "writers"})}


@pytest.mark.asyncio
async def test_advertised_schemas_and_annotations_are_exact(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        descriptors = {tool.name: tool for tool in await client.list_tools()}
    for name in (LIST, SHARE):
        descriptor = descriptors[name]
        schema = descriptor.input_schema
        if name == LIST:
            assert len(schema["anyOf"]) == 2
            for branch in schema["anyOf"]:
                assert set(branch["required"]) in ({"node_id", "query"}, {"node_id", "query", "recipient_type"})
                assert branch["additionalProperties"] is False
                assert branch["properties"]["node_id"]["format"] == "uuid"
            for scope in ({}, {"recipient_type": "group"}, {"recipient_type": "user"}):
                validate({"node_id": str(uuid4()), "query": "writers", **scope}, schema)
        assert descriptor.annotations.read_only_hint == (name == LIST)
        assert descriptor.annotations.destructive_hint is False
        assert descriptor.annotations.idempotent_hint is True
        assert descriptor.annotations.open_world_hint is False
    share = descriptors[SHARE]
    for schema, canonical, legacy in (
        (share.input_schema, "ShareNodeCommand", "ShareNodeGroupCommand"),
        (share.output_schema, "ShareNodeResult", "LegacyShareNodeGroupResult"),
    ):
        assert len(schema["anyOf"]) == 2
        definitions = {branch["title"]: branch for branch in schema["anyOf"]}
        for name, fields in (
            (canonical, {"node_id", "recipient", "permissions"}),
            (legacy, {"node_id", "group_id", "permissions"}),
        ):
            expected = fields | ({"changed"} if schema is share.output_schema else set())
            assert set(definitions[name]["properties"]) == set(definitions[name]["required"]) == expected
            assert definitions[name]["additionalProperties"] is False
            assert definitions[name]["properties"]["permissions"]["minItems"] == 1
    for recipient in ({"type": "group", "group_id": "writers"}, {"type": "user", "user_id": "observed"}):
        validate({"node_id": str(uuid4()), "recipient": recipient, "permissions": ["read"]}, share.input_schema)
    validate(arguments(SHARE, str(uuid4())), share.input_schema)
    listing = descriptors[LIST].output_schema
    assert set(listing["properties"]) == set(listing["required"]) == {"recipients", "has_more"}
    assert listing["additionalProperties"] is False
    assert "filesystem_list_sharing_groups" not in descriptors
    assert "search_users" not in descriptors
    assert LIST in share.description
    assert "omitting the display label" in share.description


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
        result = await client.call_tool(LIST, {"node_id": node_id, "query": "Current", "recipient_type": "group"})
        descriptor = next(tool for tool in await client.list_tools() if tool.name == LIST)
        blocked = await client.call_tool(SHARE, arguments(SHARE, node_id), raise_on_error=False)
        unknown = await client.call_tool(SHARE, {"node_id": node_id, "group_id": "unregistered", "permissions": ["read"]}, raise_on_error=False)
    assert result.structured_content == {
        "recipients": [{"type": "group", "group_id": group_id, "label": label}], "has_more": False,
    }
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
@pytest.mark.parametrize("tool,recipient_type", [(LIST, "legacy"), (SHARE, "legacy"), (SHARE, "group"), (SHARE, "user")])
async def test_discovery_has_no_io_and_each_invocation_captures_and_calls_once(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, tool: str, recipient_type: str,
) -> None:
    snapshot = filesystem_mcp.callers.current.get()
    node_id = uuid4()
    service = Mock(spec=FilesystemSharing)
    service.search_recipients = AsyncMock(return_value=SharingRecipientSearchResult(recipients=(), has_more=False))
    recipient = (
        UserSharingTarget(type="user", user_id="observed") if recipient_type == "user"
        else GroupSharingTarget(type="group", group_id="writers")
    )
    authoritative = ShareNodeResult(
        node_id=node_id, recipient=recipient, permissions={Permission.READ, Permission.DISCOVER}, changed=False,
    )
    service.share = AsyncMock(return_value=authoritative)
    factory = Mock(return_value=service)
    monkeypatch.setattr(filesystem_mcp.services, "sharing", factory)
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        await client.list_tools()
        assert factory.call_count == 0
        assert filesystem_mcp.callers.count == captures
        payload = (
            {"node_id": str(node_id), "recipient": recipient.model_dump(mode="json"), "permissions": ["read"]}
            if recipient_type != "legacy" else arguments(tool, str(node_id))
        )
        for _ in range(2):
            response = await client.call_tool(tool, payload)
            if recipient_type != "legacy":
                assert response.structured_content == authoritative.model_dump(mode="json")
    assert filesystem_mcp.callers.count == captures + 2
    assert factory.call_count == 2
    if tool == LIST:
        assert service.search_recipients.await_count == 2
        service.search_recipients.assert_awaited_with(snapshot, node_id, SharingRecipientSearchQuery(
            query="writers", scope=SharingScope(recipient_types=frozenset({"group", "user"})),
        ))
        service.share.assert_not_awaited()
    else:
        assert service.share.await_count == 2
        service.share.assert_awaited_with(snapshot, node_id, ShareNodePolicy(
            recipient=recipient, permissions={Permission.READ},
        ))
        service.search_recipients.assert_not_awaited()


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
    setattr(service, "share" if tool == SHARE else "search_recipients", AsyncMock(side_effect=error_type("SECRET /private")))
    monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: service)
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool(tool, arguments(tool, str(uuid4())), raise_on_error=False)
    assert result.content[0].text == expected
    assert result.structured_content is None
    assert any(sample.labels["tool_name"] == tool and sample.labels["outcome"] == "failure"
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,recipient_type", [(LIST, "legacy"), (SHARE, "legacy"), (SHARE, "group"), (SHARE, "user")])
async def test_connector_scope_excludes_sharing_before_capture(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, tool: str, recipient_type: str,
) -> None:
    factory = Mock()
    monkeypatch.setattr(filesystem_mcp.services, "sharing", factory)
    captures = filesystem_mcp.callers.count
    token = set_request_connector_scope("connector-only")
    try:
        async with Client(filesystem_mcp.server) as client:
            descriptors = await client.list_tools()
            payload = arguments(tool, str(uuid4()))
            if recipient_type != "legacy":
                payload.pop("group_id")
                payload["recipient"] = {"type": recipient_type, f"{recipient_type}_id": "observed"}
            result = await client.call_tool(tool, payload, raise_on_error=False)
        assert tool not in {descriptor.name for descriptor in descriptors}
        assert result.is_error
        assert filesystem_mcp.callers.count == captures
        factory.assert_not_called()
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
@pytest.mark.parametrize("tool_type", [FilesystemSearchSharingRecipientsTool, FilesystemShareTool])
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
async def test_cancellation_propagates(
    filesystem_mcp: FilesystemMcp, tool_type: type[FilesystemSearchSharingRecipientsTool | FilesystemShareTool], stage: str,
) -> None:
    callers = Mock(spec=FilesystemCallerCapture)
    callers.capture.return_value = filesystem_mcp.callers.current.get()
    service = Mock(spec=FilesystemSharing)
    service.search_recipients = AsyncMock(side_effect=asyncio.CancelledError())
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



@pytest.mark.asyncio
@pytest.mark.parametrize("recipient_type", ["group", "user"])
@pytest.mark.parametrize("kind", ["file", "directory"])
async def test_canonical_recipients_union_retry_and_direct_node_access(
    filesystem_mcp: FilesystemMcp, recipient_type: str, kind: str,
) -> None:
    directory = DatabaseIdentityDirectory(filesystem_mcp.database)
    await directory.observe(IdentityObservation(
        issuer="https://issuer", subject="bob", claim="groups", groups=(), name="Bob Reader",
        email="", email_verification="unknown", observed_at=datetime.now(timezone.utc),
    ))
    users = await directory.search_user_names(ScopedUserSearch(issuer="https://issuer", query="Bob", limit=50, excluded_subjects=frozenset()))
    recipient = (
        {"type": "user", "user_id": users.users[0].user_id}
        if recipient_type == "user" else {"type": "group", "group_id": "writers"}
    )
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "shared", kind)
        child_id = await create_node(client, node_id, "private-child", "file") if kind == "directory" else ""
        command = {"node_id": node_id, "recipient": recipient}
        descriptor = next(tool for tool in await client.list_tools() if tool.name == SHARE)
        first = await client.call_tool(SHARE, {**command, "permissions": ["read"]})
        second = await client.call_tool(SHARE, {**command, "permissions": ["discover"]})
        retry = await client.call_tool(SHARE, {**command, "permissions": ["discover"]})
        assert first.structured_content == {**command, "permissions": ["read"], "changed": True}
        assert second.structured_content == {**command, "permissions": ["discover", "read"], "changed": True}
        assert retry.structured_content == {**second.structured_content, "changed": False}
        for response in (first, second, retry):
            validate(response.structured_content, descriptor.output_schema)
            assert json.loads(response.content[0].text) == response.structured_content
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",) if recipient_type == "group" else (),
            AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        assert not (await client.call_tool("get_filesystem_node", {"node_id": node_id})).is_error
        if child_id:
            denied = await client.call_tool("get_filesystem_node", {"node_id": child_id}, raise_on_error=False)
            assert denied.is_error


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", [
    None, {}, {"type": "unknown", "user_id": "observed"}, {"user_id": "observed"},
    {"type": "user"}, {"type": "group"}, {"type": "user", "user_id": ""},
    {"type": "user", "user_id": " \n"}, {"type": "user", "user_id": None},
    {"type": "user", "user_id": 1},
    {"type": "group", "group_id": 1},
    {"type": "user", "user_id": "observed", "group_id": "writers"},
    *[{"type": "user", "user_id": "observed", field: "SECRET"}
      for field in ("issuer", "subject", "recursive", "owner", "label")],
])
async def test_malformed_recipient_never_captures_or_invokes_core(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, recipient: Any,
) -> None:
    factory = Mock()
    monkeypatch.setattr(filesystem_mcp.services, "sharing", factory)
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == SHARE)
        payload = {"node_id": str(uuid4()), "recipient": recipient, "permissions": ["read"]}
        with pytest.raises(SchemaValidationError):
            validate(payload, descriptor.input_schema)
        result = await client.call_tool(SHARE, payload, raise_on_error=False)
    assert result.content[0].text == "filesystem_invalid_sharing: Invalid filesystem sharing arguments"
    assert filesystem_mcp.callers.count == captures
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("patch", [
    {"group_id": "writers"}, {"user_id": "observed"}, {"issuer": "SECRET"},
    {"subject": "SECRET"}, {"recursive": True}, {"permissions": []}, {"permissions": [True]},
    {"recipient": {"type": "group", "group_id": ""}},
    {"recipient": {"type": "group", "group_id": " \n"}},
])
async def test_canonical_request_rejects_mixed_legacy_fields_and_authority(
    filesystem_mcp: FilesystemMcp, patch: dict[str, Any],
) -> None:
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        response = await client.call_tool(SHARE, {
            "node_id": str(uuid4()), "recipient": {"type": "user", "user_id": "observed"},
            "permissions": ["read"], **patch,
        }, raise_on_error=False)
    assert response.content[0].text == "filesystem_invalid_sharing: Invalid filesystem sharing arguments"
    assert filesystem_mcp.callers.count == captures
