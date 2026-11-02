import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastmcp import Client
from jsonschema import validate

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import (
    AccessGrant, ContentRef, MissingNode, Ownership, OwnershipNotFound, Permission, Principal, PrincipalType,
)
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.browsing import FilesystemBrowsing, NodeSummary
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.filesystem.deletion import FilesystemDeleteFileTool
from umbod.mcp.filesystem.ports import (
    FileDeletionApproval, FilesystemCallerCapture, FilesystemDeletionApproval, FilesystemServiceFactory,
)

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id
from .test_upload import upload

TOOL = "filesystem_delete_file"
DENIED = "filesystem_permission_denied: Filesystem access denied"


async def approve_deletion(*args: object) -> dict[str, bool]:
    return {"value": True}


@pytest.mark.asyncio
async def test_delete_removes_namespace_and_policies_retains_bytes_and_preserves_siblings(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = create_namespace_driver(database=filesystem_invocation_mcp.database)
    policies = create_access_control_driver(database=filesystem_invocation_mcp.database)
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        parent = await root_id(client)
        published = await upload(client, parent, {"encoding": "utf-8", "text": "retained payload"})
        node_id = published.structured_content["id"]
        sibling = await create_node(client, parent, "sibling", "file")
        stored = await namespace.get_node(UUID(node_id))
        assert isinstance(stored.content, ContentRef)
        sibling_owner = await policies.get_owner(UUID(sibling))
        grant = AccessGrant(
            node_id=UUID(node_id),
            principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
            permissions={Permission.DISCOVER}, recursive=False,
        )
        await policies.add_grant(grant)
        assert await policies.list_grants(UUID(node_id)) == [grant]
        forbidden_get = Mock(side_effect=AssertionError("Deletion must not read bytes"))
        forbidden_put = Mock(side_effect=AssertionError("Deletion must not write bytes"))
        with monkeypatch.context() as patches:
            patches.setattr(filesystem_invocation_mcp.content, "get", forbidden_get)
            patches.setattr(filesystem_invocation_mcp.content, "put", forbidden_put)
            captures = filesystem_invocation_mcp.callers.count
            result = await client.call_tool(TOOL, {
                "node_id": node_id, "expected_revision": published.structured_content["revision"],
            })
            assert filesystem_invocation_mcp.callers.count == captures + 3
        forbidden_get.assert_not_called()
        forbidden_put.assert_not_called()
        assert result.content[0].text == "File deleted successfully."
        assert result.structured_content == {"node_id": node_id, "deleted": True}
        descriptor = next(tool for tool in await client.list_tools() if tool.name == TOOL)
        validate(result.structured_content, descriptor.output_schema)
        listing = await client.call_tool("filesystem_browse", {"operation": "ls", "target": {"type": "root"}})
        assert [node["id"] for node in listing.structured_content["result"]["entries"]] == [sibling]
        repeated = await client.call_tool(TOOL, {
            "node_id": node_id, "expected_revision": published.structured_content["revision"],
        }, raise_on_error=False)
        assert repeated.is_error
        assert repeated.content[0].text == DENIED
    with pytest.raises(MissingNode):
        await namespace.get_node(UUID(node_id))
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(UUID(node_id))
    assert await policies.list_grants(UUID(node_id)) == []
    assert await policies.get_owner(UUID(sibling)) == sibling_owner
    assert b"".join([chunk async for chunk in filesystem_invocation_mcp.content.get(stored.content.key)]) == b"retained payload"
    assert any(sample.labels["tool_name"] == TOOL and sample.labels["outcome"] == "success"
               for sample in filesystem_invocation_mcp.metrics.metric_samples())


@pytest.mark.asyncio
async def test_stale_revision_preserves_node_and_policy(filesystem_invocation_mcp: FilesystemMcp) -> None:
    policies = create_access_control_driver(database=filesystem_invocation_mcp.database)
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        node_id = await create_node(client, await root_id(client), "file", "file")
        before = await client.call_tool("get_filesystem_node", {"node_id": node_id})
        owner = await policies.get_owner(UUID(node_id))
        grant = AccessGrant(
            node_id=UUID(node_id),
            principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
            permissions={Permission.DISCOVER}, recursive=False,
        )
        await policies.add_grant(grant)
        result = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 2}, raise_on_error=False)
        after = await client.call_tool("get_filesystem_node", {"node_id": node_id})
    assert result.is_error
    assert result.content[0].text == "filesystem_revision_conflict: Filesystem revision conflict"
    assert {key: value for key, value in before.structured_content.items() if key != "visible_to"} == {key: value for key, value in after.structured_content.items() if key != "visible_to"}
    assert after.structured_content["visible_to"]["grants"] == [grant.model_dump(mode="json")]
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == [grant]
    assert any(sample.labels["tool_name"] == TOOL and sample.labels["outcome"] == "failure"
               for sample in filesystem_invocation_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [1, 999])
async def test_missing_and_unauthorized_nodes_have_identical_safe_errors(
    filesystem_invocation_mcp: FilesystemMcp, revision: int,
) -> None:
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        denied = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": revision}, raise_on_error=False)
        missing = await client.call_tool(TOOL, {"node_id": str(uuid4()), "expected_revision": revision}, raise_on_error=False)
    assert denied.is_error and missing.is_error
    assert denied.content == missing.content
    assert denied.content[0].text == DENIED


@pytest.mark.asyncio
@pytest.mark.parametrize("root", [False, True])
async def test_authorized_directory_and_root_are_rejected(filesystem_invocation_mcp: FilesystemMcp, root: bool) -> None:
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        parent = await root_id(client)
        node_id = parent if root else await create_node(client, parent, "folder", "directory")
        if root:
            await create_access_control_driver(database=filesystem_invocation_mcp.database).set_owner(Ownership(
                node_id=UUID(node_id), owner=Principal(type=PrincipalType.USER, issuer="https://issuer", id="alice"),
            ))
        result = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 999}, raise_on_error=False)
        preserved = await client.call_tool("get_filesystem_node", {"node_id": node_id})
    assert result.is_error
    assert result.content[0].text == "filesystem_wrong_node_kind: Invalid filesystem node kind"
    assert preserved.structured_content["id"] == node_id


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {}, {"node_id": str(uuid4())}, {"expected_revision": 1},
    {"node_id": "not-a-uuid", "expected_revision": 1},
    *[{"node_id": str(uuid4()), "expected_revision": revision}
      for revision in (True, False, 1.0, "1", 0, -1, None, 10_000_000_000_000_000_000)],
    *[{"node_id": str(uuid4()), "expected_revision": 1, field: "SECRET"}
      for field in ("caller", "owner", "identity", "groups", "grants", "storage_key", "content")],
])
async def test_delete_rejects_invalid_arguments_without_capturing_identity(
    filesystem_invocation_mcp: FilesystemMcp, arguments: dict[str, Any],
) -> None:
    captures = filesystem_invocation_mcp.callers.count
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        result = await client.call_tool(TOOL, arguments, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "filesystem_invalid_delete: Invalid file deletion arguments"
    assert filesystem_invocation_mcp.callers.count == captures


@pytest.mark.asyncio
async def test_maximum_revision_is_validated_without_coercion(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        node_id = await create_node(client, await root_id(client), "file", "file")
        result = await client.call_tool(TOOL, {
            "node_id": node_id, "expected_revision": 9_999_999_999_999_999_999,
        }, raise_on_error=False)
    assert result.content[0].text == "filesystem_revision_conflict: Filesystem revision conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.LOCAL_SEMANTIC,
])
async def test_delete_requires_current_verified_identity(
    filesystem_invocation_mcp: FilesystemMcp, provenance: AuthenticationProvenance,
) -> None:
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        node_id = await create_node(client, await root_id(client), "file", "file")
        filesystem_invocation_mcp.callers.current.set(caller_snapshot("alice", "https://issuer", ("writers",), provenance))
        result = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == DENIED


@pytest.mark.asyncio
async def test_direct_node_grant_authorizes_without_parent_access_and_revocation_is_fresh(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    policies = create_access_control_driver(database=filesystem_invocation_mcp.database)
    principal = Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob")
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        node_id = await create_node(client, await root_id(client), "file", "file")
        grant = AccessGrant(node_id=UUID(node_id), principal=principal,
                            permissions={Permission.DISCOVER, Permission.DELETE}, recursive=False)
        await policies.add_grant(grant)
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        await client.call_tool("get_filesystem_node", {"node_id": node_id})
        await policies.remove_grant(UUID(node_id), principal)
        revoked = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False)
        assert revoked.is_error
        assert revoked.content[0].text == DENIED
        await policies.add_grant(grant)
        deleted = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1})
    assert deleted.structured_content == {"node_id": node_id, "deleted": True}


@pytest.mark.asyncio
async def test_delete_schema_declares_only_revision_and_node_and_destructive_annotations(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == TOOL)
    schema = descriptor.input_schema
    assert set(schema["properties"]) == set(schema["required"]) == {"node_id", "expected_revision"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["node_id"]["format"] == "uuid"
    assert schema["properties"]["expected_revision"]["type"] == "integer"
    assert schema["properties"]["expected_revision"]["minimum"] == 1
    assert schema["properties"]["expected_revision"]["maximum"] == 9_999_999_999_999_999_999
    assert set(descriptor.output_schema["properties"]) == {"node_id", "deleted"}
    assert descriptor.annotations.read_only_hint is False
    assert descriptor.annotations.destructive_hint is True
    assert descriptor.annotations.idempotent_hint is False
    assert descriptor.annotations.open_world_hint is False


@pytest.mark.asyncio
async def test_connector_scope_hides_delete_and_blocks_direct_invocation_before_capture(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        node_id = await create_node(client, await root_id(client), "file", "file")
    captures = filesystem_invocation_mcp.callers.count
    token = set_request_connector_scope("connector-only")
    try:
        async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
            descriptors = await client.list_tools()
            result = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False)
        assert TOOL not in {tool.name for tool in descriptors}
        assert result.is_error
        assert filesystem_invocation_mcp.callers.count == captures
    finally:
        reset_request_connector_scope(token)
    async with Client(filesystem_invocation_mcp.server, elicitation_handler=approve_deletion) as client:
        deleted = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1})
    assert deleted.structured_content == {"node_id": node_id, "deleted": True}


@dataclass
class DeletionDependencies:
    callers: Mock
    factory: Mock
    service: Mock
    browsing: Mock
    approval: Mock
    node: NodeSummary

    def tool(self) -> FilesystemDeleteFileTool:
        return FilesystemDeleteFileTool(self.callers, self.factory, self.approval)


@pytest_asyncio.fixture
async def deletion_dependencies(filesystem_invocation_mcp: FilesystemMcp) -> DeletionDependencies:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "file", "file")
    caller = filesystem_invocation_mcp.callers.current.get()
    node = await filesystem_invocation_mcp.services.browsing().get_node(caller, UUID(node_id))
    callers = Mock(spec=FilesystemCallerCapture)
    callers.capture.return_value = caller
    service = Mock(spec=FilesystemDeletion)
    service.check_delete_eligibility = AsyncMock()
    service.delete_file = AsyncMock()
    browsing = Mock(spec=FilesystemBrowsing)
    browsing.get_node = AsyncMock(return_value=node)
    factory = Mock(spec=FilesystemServiceFactory)
    factory.deletion.return_value = service
    factory.browsing.return_value = browsing
    approval = Mock(spec=FilesystemDeletionApproval)
    approval.confirm = AsyncMock(return_value=FileDeletionApproval.APPROVED)
    return DeletionDependencies(callers, factory, service, browsing, approval, node)


@pytest.mark.asyncio
async def test_each_delete_recaptures_after_approval_and_creates_a_fresh_operation_service(
    deletion_dependencies: DeletionDependencies,
) -> None:
    dependencies = deletion_dependencies
    services = [dependencies.service, Mock(spec=FilesystemDeletion)]
    services[1].check_delete_eligibility = AsyncMock()
    services[1].delete_file = AsyncMock()
    dependencies.factory.deletion.side_effect = services
    tool = dependencies.tool()
    for revision in (1, 2):
        dependencies.browsing.get_node.return_value = dependencies.node.model_copy(update={"revision": revision})
        await tool.run({"node_id": str(dependencies.node.id), "expected_revision": revision})
    assert dependencies.callers.capture.call_count == 4
    assert dependencies.factory.deletion.call_count == 2
    for revision, service in enumerate(services, start=1):
        service.delete_file.assert_awaited_once_with(
            dependencies.callers.capture.return_value, dependencies.node.id, expected_revision=revision,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "eligibility", "browsing", "approval", "service"])
async def test_delete_cancellation_propagates_from_each_operation_stage(
    deletion_dependencies: DeletionDependencies, stage: str,
) -> None:
    dependencies = deletion_dependencies
    operation = {
        "capture": dependencies.callers.capture,
        "factory": dependencies.factory.deletion,
        "eligibility": dependencies.service.check_delete_eligibility,
        "browsing": dependencies.browsing.get_node,
        "approval": dependencies.approval.confirm,
        "service": dependencies.service.delete_file,
    }[stage]
    operation.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await dependencies.tool().run({"node_id": str(dependencies.node.id), "expected_revision": 1})
