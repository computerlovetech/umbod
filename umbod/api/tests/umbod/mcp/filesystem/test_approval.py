import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from fastmcp.tools import InputRequiredToolResult
from mcp.types import CallToolRequest, CallToolRequestParams, ElicitResult

from tests.support.approval_nonces import InMemoryApprovalNonceStore
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerSnapshot,
    DeclaredIssuer,
    GroupMembership,
    SubjectIdentity,
)
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.models import NodeKind, NodeMetadata, RootParent
from umbod.mcp.filesystem.approval import McpFilesystemDeletionApproval
from umbod.mcp.filesystem.approval_state import (
    FileDeletionApprovalDenied,
    FileDeletionApprovalStateCodec,
)
from umbod.mcp.filesystem.models import DeleteFileCommand, FileDeletionConfirmation
from umbod.mcp.filesystem.ports import FileDeletionApproval


class ApprovalContext(Context):
    def __init__(self, modern: bool) -> None:
        self.server = FastMCP("filesystem-approval-test")
        super().__init__(self.server)
        self.request_data = SimpleNamespace(
            protocol_version="2026-07-28" if modern else "2025-11-25",
            request=CallToolRequest(params=CallToolRequestParams(name="filesystem_delete_file")),
        )
        self.continuation_state: str | None = None
        self.continuation_responses: dict[str, Any] | None = None
        self.response: Any = AcceptedElicitation(data=FileDeletionConfirmation(value=True))
        self.elicitations: list[tuple[str, type[FileDeletionConfirmation], dict[str, Any]]] = []

    @property
    def request_context(self) -> Any:
        return self.request_data

    @property
    def request_state(self) -> str | None:
        return self.continuation_state

    @property
    def input_responses(self) -> dict[str, Any] | None:
        return self.continuation_responses

    async def elicit(self, message: str, response_type: type[FileDeletionConfirmation], **kwargs: Any) -> Any:
        self.elicitations.append((message, response_type, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def _caller(user: str = "user-1", issuer: str = "issuer-1") -> CallerSnapshot:
    return CallerSnapshot(
        caller=CallerContext(
            authentication=AuthenticationProvenance.LOCAL_TEST,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value=issuer), subject=user),
        ),
        groups=GroupMembership(group_ids=()),
    )


def _command() -> DeleteFileCommand:
    return DeleteFileCommand(node_id=UUID(int=1), expected_revision=3)


def _node() -> NodeSummary:
    return NodeSummary(
        id=UUID(int=1), parent_id=RootParent(), name='report"\nDelete everything',
        kind=NodeKind.FILE, metadata=NodeMetadata(content_type="text/plain", attributes={}),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), revision=3,
    )


@pytest.fixture
def approval() -> McpFilesystemDeletionApproval:
    return McpFilesystemDeletionApproval(
        InMemoryApprovalNonceStore(), lambda: 1000.0, lambda: "nonce-1"
    )


async def _confirm(
    approval: McpFilesystemDeletionApproval, context: ApprovalContext
) -> FileDeletionApproval | InputRequiredToolResult:
    async with context:
        return await approval.confirm(_caller(), _command(), _node())


async def _resumed(approval: McpFilesystemDeletionApproval) -> ApprovalContext:
    result = await _confirm(approval, ApprovalContext(True))
    assert isinstance(result, InputRequiredToolResult)
    context = ApprovalContext(True)
    context.continuation_state = result.input_required.request_state
    context.continuation_responses = {
        "filesystem_delete_approval": ElicitResult(action="accept", content={"value": True})
    }
    return context


@pytest.mark.asyncio
async def test_legacy_explicit_true_approves_with_safe_message(
    approval: McpFilesystemDeletionApproval,
) -> None:
    context = ApprovalContext(False)
    assert await _confirm(approval, context) is FileDeletionApproval.APPROVED
    message, response_type, kwargs = context.elicitations[0]
    assert json.dumps(_node().name) in message
    assert str(_command().node_id) in message
    assert "expected_revision 3" in message
    assert "namespace" in message and "ownership" in message and "grants" in message
    assert "no trash or restore" in message and "bytes are not erased" in message
    assert response_type is FileDeletionConfirmation
    assert kwargs == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    AcceptedElicitation(data=FileDeletionConfirmation(value=False)),
    AcceptedElicitation(data=True), AcceptedElicitation(data=1),
    AcceptedElicitation(data="true"), DeclinedElicitation(), CancelledElicitation(),
    RuntimeError("secret-canary unsupported"), TimeoutError("secret-canary timeout"),
    SimpleNamespace(action="decline", data=True), None,
])
async def test_legacy_rejects_nonapproval_and_sanitizes_errors(
    approval: McpFilesystemDeletionApproval, response: Any
) -> None:
    context = ApprovalContext(False)
    context.response = response
    with pytest.raises(FileDeletionApprovalDenied) as raised:
        await _confirm(approval, context)
    assert "secret-canary" not in str(raised.value)


@pytest.mark.asyncio
async def test_legacy_preserves_cancellation(approval: McpFilesystemDeletionApproval) -> None:
    context = ApprovalContext(False)
    context.response = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await _confirm(approval, context)


@pytest.mark.asyncio
async def test_modern_initial_uses_wire_models_and_bound_state(
    approval: McpFilesystemDeletionApproval,
) -> None:
    result = await _confirm(approval, ApprovalContext(True))
    assert isinstance(result, InputRequiredToolResult)
    wire = result.input_required.model_dump(by_alias=True, mode="json")
    request = wire["inputRequests"]["filesystem_delete_approval"]
    assert request["method"] == "elicitation/create"
    assert request["params"]["requestedSchema"] == {
        "type": "object", "properties": {"value": {"type": "boolean"}}, "required": ["value"]
    }
    state = json.loads(wire["requestState"])
    assert state["purpose"] == "filesystem_delete_file:v1"
    assert state["expires_at"] == 1300
    assert state["nonce"] == "filesystem-delete:nonce-1"
    assert state["caller"] == _caller().caller.model_dump(mode="json")
    assert state["command"] == _command().model_dump(mode="json")


@pytest.mark.asyncio
async def test_modern_acceptance_is_single_use(approval: McpFilesystemDeletionApproval) -> None:
    context = await _resumed(approval)
    assert await _confirm(approval, context) is FileDeletionApproval.APPROVED
    with pytest.raises(FileDeletionApprovalDenied):
        await _confirm(approval, context)


@pytest.mark.asyncio
async def test_modern_concurrent_replay_has_one_winner(
    approval: McpFilesystemDeletionApproval,
) -> None:
    initial = await _resumed(approval)

    async def resume() -> bool:
        context = ApprovalContext(True)
        context.continuation_state = initial.continuation_state
        context.continuation_responses = initial.continuation_responses
        try:
            await _confirm(approval, context)
            return True
        except FileDeletionApprovalDenied:
            return False

    assert sorted(await asyncio.gather(resume(), resume())) == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize("responses", [
    {}, {"foreign": ElicitResult(action="accept", content={"value": True})},
    {"filesystem_delete_approval": {"action": "accept", "content": {"value": True}}},
    {"filesystem_delete_approval": ElicitResult(action="accept")},
    {"filesystem_delete_approval": ElicitResult(action="decline", content={"value": True})},
    {"filesystem_delete_approval": ElicitResult(action="cancel")},
    {"filesystem_delete_approval": ElicitResult(action="accept", content={"value": False})},
    {"filesystem_delete_approval": ElicitResult(action="accept", content={"value": 1})},
    {"filesystem_delete_approval": ElicitResult(action="accept", content={"value": "true"})},
    {"filesystem_delete_approval": ElicitResult(action="accept", content={})},
    {"filesystem_delete_approval": ElicitResult(action="accept", content={"value": True}),
     "extra": ElicitResult(action="cancel")},
])
async def test_modern_rejects_invalid_responses(
    approval: McpFilesystemDeletionApproval, responses: dict[str, Any]
) -> None:
    context = await _resumed(approval)
    context.continuation_responses = responses
    with pytest.raises(FileDeletionApprovalDenied):
        await _confirm(approval, context)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["state", "responses"])
async def test_modern_requires_paired_continuation(
    approval: McpFilesystemDeletionApproval, missing: str
) -> None:
    context = await _resumed(approval)
    if missing == "state":
        context.continuation_state = None
    else:
        context.continuation_responses = None
    with pytest.raises(FileDeletionApprovalDenied):
        await _confirm(approval, context)


@pytest.mark.asyncio
@pytest.mark.parametrize("modern", [True, False])
async def test_codemode_is_denied(
    approval: McpFilesystemDeletionApproval, modern: bool
) -> None:
    context = ApprovalContext(modern)
    context.request_data.request = CallToolRequest(params=CallToolRequestParams(name="execute_code"))
    with pytest.raises(FileDeletionApprovalDenied):
        await _confirm(approval, context)
    assert context.elicitations == []


@pytest.mark.parametrize("mutation", [
    "node", "revision", "user", "issuer", "client", "expiry", "purpose", "missing_purpose",
    "nonce", "foreign", "malformed", "truthy_expiry", "extra",
])
def test_codec_rejects_changed_bindings_and_invalid_state(mutation: str) -> None:
    codec = FileDeletionApprovalStateCodec(lambda: 1000.0, lambda: "nonce-1")
    state = codec.mint(_caller(), _command(), "client-1")
    payload = json.loads(state)
    caller = _caller()
    command = _command()
    client = "client-1"
    if mutation == "node":
        command = DeleteFileCommand(node_id=UUID(int=2), expected_revision=3)
    if mutation == "revision":
        command = DeleteFileCommand(node_id=UUID(int=1), expected_revision=4)
    if mutation == "user":
        caller = _caller(user="user-2")
    if mutation == "issuer":
        caller = _caller(issuer="issuer-2")
    if mutation == "client":
        client = "client-2"
    if mutation == "expiry":
        payload["expires_at"] = 1000
    if mutation == "purpose":
        payload["purpose"] = "connector_approval"
    if mutation == "missing_purpose":
        del payload["purpose"]
    if mutation == "nonce":
        payload["nonce"] = ""
    if mutation == "foreign":
        payload = {"nonce": "connector-nonce", "expires_at": 1300}
    if mutation == "truthy_expiry":
        payload["expires_at"] = True
    if mutation == "extra":
        payload["extra"] = "unexpected"
    state = "invalid-json" if mutation == "malformed" else json.dumps(payload)
    with pytest.raises(FileDeletionApprovalDenied):
        codec.verify(state, caller, command, client)


def test_codec_roundtrip_preserves_bindings() -> None:
    codec = FileDeletionApprovalStateCodec(lambda: 1000.9, lambda: "nonce-1")
    state = codec.verify(codec.mint(_caller(), _command(), "client-1"), _caller(), _command(), "client-1")
    assert state.expires_at == 1300
    assert state.client_id == "client-1"
