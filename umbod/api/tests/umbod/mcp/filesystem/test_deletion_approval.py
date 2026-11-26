import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import FastMCPTransport
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ElicitResult as WireElicitResult, InputRequiredResult

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import (
    ContentRef, MissingNode, OwnershipNotFound,
)
from umbod.core.filesystem.deletion.service import DeletionService
from umbod.core.system_settings import UpdateSystemSettings, create_system_settings_service
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from tests.umbod.mcp.test_http_transport import HEADERS, rpc_result
from umbod.mcp.http_transport import MAX_MCP_REQUEST_BODY_BYTES, create_mcp_http_app
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink, StdoutMcpToolInvocationLogSink

from .conftest import FilesystemMcp, FilesystemState, caller_snapshot, create_filesystem_server
from .test_browsing import create_node
from .test_visibility import shared_namespace, save_namespace_access, select_caller
from umbod.core.filesystem.namespaces.models import SharedNamespaceView

TOOL = "filesystem_delete_file"


class RecordingClientSession:
    def __init__(
        self, session: Any, observed_states: list[tuple[str | None, str | None]], tamper: bool,
    ) -> None:
        self.session = session
        self.observed_states = observed_states
        self.tamper = tamper

    async def call_tool(self, *args: object, **kwargs: Any) -> Any:
        request_state = kwargs.get("request_state")
        if self.tamper and isinstance(request_state, str):
            kwargs["request_state"] = request_state + "tampered"
        result = await self.session.call_tool(*args, **kwargs)
        self.observed_states.append((
            kwargs.get("request_state"),
            result.request_state if isinstance(result, InputRequiredResult) else None,
        ))
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.session, name)


class RecordingFastMCPTransport(FastMCPTransport):
    def __init__(self, server: FastMCP, *, tamper: bool = False) -> None:
        super().__init__(server)
        self.observed_states: list[tuple[str | None, str | None]] = []
        self.tamper = tamper

    @asynccontextmanager
    async def connect_session(self, **kwargs: Any) -> AsyncIterator[RecordingClientSession]:
        async with super().connect_session(**kwargs) as session:
            yield RecordingClientSession(session, self.observed_states, self.tamper)


def deletion_successes(filesystem: FilesystemMcp) -> list[float]:
    return [
        sample.value for sample in filesystem.metrics.metric_samples()
        if sample.labels.get("tool_name") == TOOL and sample.labels.get("outcome") == "success"
        and sample.value > 0
    ]


async def prepare_file(filesystem: FilesystemMcp) -> tuple[str, SharedNamespaceView]:
    policy = await shared_namespace(filesystem)
    select_caller(filesystem, "alice", (policy.groups[0].group_id,))
    async with Client(filesystem.server) as client:
        node_id = await create_node(client, str(policy.root_node_id), "approval-target", "file")
    return node_id, policy


@pytest.mark.asyncio
@pytest.mark.parametrize("disable_while_pending", [False, True])
async def test_signed_continuation_echoes_unchanged_and_deletes_only_after_acceptance(
    filesystem_state: FilesystemState, disable_while_pending: bool,
) -> None:
    logs = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    filesystem = create_filesystem_server(filesystem_state, filtered=False, invocation_logs=logs)
    node_id, _ = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    transport = RecordingFastMCPTransport(filesystem.server)
    callbacks: list[bool] = []
    def deletion_outcomes() -> list[str]:
        return [
            record.attributes["mcp.invocation.outcome"] for record in logs.invocation_records()
            if record.attributes["mcp.tool.name"] == TOOL
        ]

    async def accept(*args: object) -> dict[str, bool]:
        callbacks.append(True)
        assert transport.observed_states[0][0] is None
        assert transport.observed_states[0][1].startswith("v1.")
        assert await namespace.get_node(UUID(node_id)) == before
        assert await policies.get_owner(UUID(node_id)) == owner
        assert await policies.list_grants(UUID(node_id)) == []
        assert deletion_successes(filesystem) == []
        assert deletion_outcomes() == []
        if disable_while_pending:
            await disable_approval(filesystem)
        return {"value": True}

    async with Client(transport, elicitation_handler=accept) as client:
        result = await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1})
        metrics = deletion_successes(filesystem)
        assert deletion_outcomes() == ["success"]
        repeated = await client.call_tool(
            TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
        )
    assert result.structured_content == {"node_id": node_id, "deleted": True}
    assert callbacks == [True]
    sealed_state = transport.observed_states[0][1]
    assert transport.observed_states[1] == (sealed_state, None)
    assert repeated.is_error
    assert metrics == [1.0, 1.0]
    assert deletion_successes(filesystem) == metrics
    assert deletion_outcomes() == ["success", "failure"]
    with pytest.raises(MissingNode):
        await namespace.get_node(UUID(node_id))
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(UUID(node_id))
    assert await policies.list_grants(UUID(node_id)) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["false", "decline", "cancel", "no-handler"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_denied_approval_preserves_node_and_namespace_authority(
    filesystem_invocation_mcp: FilesystemMcp, response: str, mode: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))

    async def deny(*args: object) -> dict[str, bool] | ElicitResult[dict[str, bool]]:
        if response == "false":
            return {"value": False}
        return ElicitResult(action=response)

    async with Client(
        filesystem.server, mode=mode, elicitation_handler=None if response == "no-handler" else deny,
    ) as client:
        if response == "no-handler" and mode == "auto":
            with pytest.raises(MCPError, match="Elicitation not supported"):
                await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1})
        else:
            result = await client.call_tool(
                TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
            )
            assert result.is_error
            if response != "no-handler":
                guidance = result.meta["computerlove.tech/umbod"]["guidance"]
                assert guidance["outcome"] == "failure"
                assert guidance["operation_state"] == "not_started"
                assert guidance["error"]["code"] == "filesystem_delete_approval_denied"
                assert guidance["recovery"]["retry"] == "never"
                assert "Do not retry this operation." in result.content[1].text
                assert "After decline or cancellation, stop." in result.content[1].text
                assert "Obtain the required permission" not in result.content[1].text
                assert guidance["recovery"]["instructions"]
                for instruction in guidance["recovery"]["instructions"]:
                    assert instruction in result.content[1].text
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


@pytest.mark.asyncio
async def test_stateless_legacy_http_cannot_delete_without_backchannel(
    filesystem_state: FilesystemState, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    output = StringIO()
    filesystem = create_filesystem_server(
        filesystem_state, filtered=False,
        invocation_logs=StdoutMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter(), output),
    )
    delete_file = AsyncMock()
    monkeypatch.setattr(DeletionService, "delete_file", delete_file)
    node_id, _ = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    app = create_mcp_http_app(
        filesystem.server, path="/mcp", stateless_http=True,
        max_request_body_bytes=MAX_MCP_REQUEST_BODY_BYTES,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
            response = await client.post("/mcp", headers={**HEADERS, "MCP-Protocol-Version": "2025-11-25"}, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": TOOL, "arguments": {"node_id": node_id, "expected_revision": 1}},
            })
            result = rpc_result(response)
    assert result["isError"]
    assert "Deletion cancelled: approval is required, but the confirmation prompt could not be delivered. No files were deleted." in result["content"][0]["text"]
    assert "only on renewed explicit user request" in result["content"][1]["text"]
    guidance = result["_meta"]["computerlove.tech/umbod"]["guidance"]
    assert guidance["error"]["code"] == "filesystem_delete_approval_unavailable"
    assert guidance["operation_state"] == "not_started"
    assert guidance["recovery"]["retry"] == "never"
    delete_file.assert_not_called()

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    deletion_record, = (record for record in records if record["attributes"]["mcp.tool.name"] == TOOL)
    assert deletion_record["severity_text"] == "WARNING"
    assert deletion_record["attributes"]["mcp.failure.category"] == "authorization"
    assert all(record.levelname not in {"ERROR", "CRITICAL"} for record in caplog.records)
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [1, "true", "yes"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_nonboolean_wire_approval_cannot_delete(
    filesystem_invocation_mcp: FilesystemMcp, value: object, mode: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))

    async def approve_with_nonboolean(*args: object) -> ElicitResult[dict[str, object]]:
        return ElicitResult(action="accept", content={"value": value})

    async with Client(filesystem.server, mode=mode, elicitation_handler=approve_with_nonboolean) as client:
        if mode == "auto":
            with pytest.raises(MCPError, match="is not of type 'boolean'"):
                await client.call_tool(
                    TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
                )
        else:
            result = await client.call_tool(
                TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
            )
            assert result.is_error
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


async def disable_approval(filesystem: FilesystemMcp) -> None:
    await create_system_settings_service(filesystem.database).set_settings(
        "administrator", UpdateSystemSettings(require_mcp_file_deletion_approval=False),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("approval_response", [
    None,
    WireElicitResult(action="decline"),
    WireElicitResult(action="accept", content={"value": 1}),
    WireElicitResult(action="accept", content={"value": "true"}),
    WireElicitResult(action="accept", content={"value": "yes"}),
])
async def test_disabled_policy_does_not_authorize_invalid_continuation(
    filesystem_invocation_mcp: FilesystemMcp, approval_response: WireElicitResult | None,
) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    arguments = {"node_id": node_id, "expected_revision": 1}

    async with Client(filesystem.server) as client:
        pending = await client.session.call_tool(TOOL, arguments, allow_input_required=True)
        assert isinstance(pending, InputRequiredResult)
        await disable_approval(filesystem)
        result = await client.session.call_tool(
            TOOL, arguments,
            request_state=pending.request_state,
            input_responses=None if approval_response is None else {"filesystem_delete_approval": approval_response},
        )

    assert isinstance(result, CallToolResult)
    assert result.is_error
    assert result.meta["computerlove.tech/umbod"]["guidance"]["operation_state"] == "not_started"
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


@pytest.mark.asyncio
async def test_tampered_signed_continuation_cannot_delete(filesystem_invocation_mcp: FilesystemMcp) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    transport = RecordingFastMCPTransport(filesystem.server, tamper=True)

    async def accept(*args: object) -> dict[str, bool]:
        return {"value": True}

    async with Client(transport, elicitation_handler=accept) as client:
        with pytest.raises(MCPError, match="Invalid or expired requestState"):
            await client.call_tool(TOOL, {"node_id": node_id, "expected_revision": 1})
    assert transport.observed_states[0][1].startswith("v1.")
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_permission_revoked_during_approval_prevents_final_delete(
    filesystem_invocation_mcp: FilesystemMcp, mode: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    filesystem.callers.current.set(caller_snapshot(
        "bob", "https://issuer", (policy.groups[0].group_id,), AuthenticationProvenance.UPSTREAM_VERIFIED,
    ))
    callbacks: list[bool] = []

    async def revoke(*args: object) -> dict[str, bool]:
        callbacks.append(True)
        await save_namespace_access(filesystem, policy, None)
        return {"value": True}

    async with Client(filesystem.server, mode=mode, elicitation_handler=revoke) as client:
        result = await client.call_tool(
            TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
        )
    assert callbacks == [True]
    assert result.is_error
    assert result.content[0].text == "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask an administrator for namespace access."
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_revision_changed_during_approval_prevents_final_delete(
    filesystem_invocation_mcp: FilesystemMcp, mode: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    owner = await policies.get_owner(UUID(node_id))

    async def revise(*args: object) -> dict[str, bool]:
        await namespace.update_node(
            UUID(node_id), content=ContentRef(key="approval-revision", size=0), expected_revision=1,
        )
        return {"value": True}

    async with Client(filesystem.server, mode=mode, elicitation_handler=revise) as client:
        result = await client.call_tool(
            TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
        )
    assert result.is_error
    assert result.content[0].text == "filesystem_revision_conflict: Filesystem revision conflict. Read the current node, review its changes, and retry with its current revision."
    assert (await namespace.get_node(UUID(node_id))).revision == 2
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["subject", "groups"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_changed_caller_during_approval_cannot_delete(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, change: str, mode: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    node_id, policy = await prepare_file(filesystem)
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    initial = filesystem.callers.capture()
    if change == "groups":
        initial = caller_snapshot("bob", "https://issuer", (policy.groups[0].group_id,), AuthenticationProvenance.UPSTREAM_VERIFIED)
    capture = Mock(return_value=initial)
    monkeypatch.setattr(filesystem.callers, "capture", capture)
    callbacks: list[bool] = []

    async def change_identity(*args: object) -> dict[str, bool]:
        callbacks.append(True)
        capture.return_value = caller_snapshot(
            "bob", "https://issuer",
            () if change == "groups" else (policy.groups[0].group_id,), AuthenticationProvenance.UPSTREAM_VERIFIED,
        )
        return {"value": True}

    async with Client(filesystem.server, mode=mode, elicitation_handler=change_identity) as client:
        result = await client.call_tool(
            TOOL, {"node_id": node_id, "expected_revision": 1}, raise_on_error=False,
        )
    assert callbacks == [True]
    assert result.is_error
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == []
    assert deletion_successes(filesystem) == []
