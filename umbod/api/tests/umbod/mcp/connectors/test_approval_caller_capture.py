import json

import pytest
from pydantic import ValidationError

from umbod.core.invocation import ConnectorInvocation, ConnectorInvocationDenied
from umbod.mcp.connectors.native import ApprovalCallerBinding, ApprovalStateCodec
from umbod.mcp.connectors.native.approval_principal import (
    ApprovalActorIdentity,
    CurrentInvocationApprovalCallerCapture,
)
from umbod.mcp.logging import (
    McpInvocationActor,
    McpInvocationContext,
    McpInvocationCorrelation,
    set_mcp_invocation_context,
)


def _set_actor(actor: McpInvocationActor) -> None:
    set_mcp_invocation_context(
        McpInvocationContext(
            actor=actor,
            correlation=McpInvocationCorrelation(trace_id="trace"),
            server_name="approval-test",
        )
    )


def _invocation() -> ConnectorInvocation:
    return ConnectorInvocation.create(
        connector_kind="native",
        connector_id="connector",
        operation_name="send",
        public_tool_name="connector_send",
        arguments={},
    )


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        (
            McpInvocationActor(agent_client_id="client", session_id="session"),
            {"agent_client_id": "client"},
        ),
        (
            McpInvocationActor(authenticated_user_id="fallback-email", session_id="session"),
            {"authenticated_user_id": "fallback-email"},
        ),
        (
            McpInvocationActor(
                agent_client_id="client", authenticated_user_id="user", session_id="session"
            ),
            {"agent_client_id": "client", "authenticated_user_id": "user"},
        ),
        (McpInvocationActor(session_id="session"), {"session_id": "session"}),
    ],
)
def test_capture_preserves_legacy_wire_identity_without_authentication(
    actor: McpInvocationActor, expected: dict[str, str]
) -> None:
    _set_actor(actor)
    capture = CurrentInvocationApprovalCallerCapture()
    binding = capture.capture()
    codec = ApprovalStateCodec(clock=lambda: 1000.0, random_token=lambda: "nonce", ttl_seconds=300)
    token = codec.mint(_invocation(), 1, binding)
    _set_actor(McpInvocationActor(session_id="other-session"))

    assert json.loads(token)["principal"] == expected
    assert codec.verify(token, _invocation(), 1, binding) == {
        "nonce": "nonce",
        "expires_at": 1300,
    }
    with pytest.raises(ConnectorInvocationDenied, match="state invalid"):
        codec.verify(token, _invocation(), 1, capture.capture())


def test_capture_without_actor_identity_is_denied() -> None:
    _set_actor(McpInvocationActor())

    with pytest.raises(ConnectorInvocationDenied, match="requires identity"):
        CurrentInvocationApprovalCallerCapture().capture()


def test_captured_identity_is_frozen_required_and_extra_forbidden() -> None:
    identity = ApprovalActorIdentity(agent_client_id="client", authenticated_user_id="")
    binding = ApprovalCallerBinding(identity=identity)

    with pytest.raises(ValidationError):
        binding.identity = identity
    with pytest.raises(ValidationError):
        identity.agent_client_id = "other"
    with pytest.raises(ValidationError):
        ApprovalCallerBinding.model_validate({})
    with pytest.raises(ValidationError):
        ApprovalCallerBinding.model_validate({"identity": identity, "unexpected": "value"})
    with pytest.raises(ValidationError):
        ApprovalActorIdentity(agent_client_id="", authenticated_user_id="")
