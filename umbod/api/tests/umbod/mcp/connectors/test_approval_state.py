from collections.abc import Mapping

import pytest

from umbod.core.invocation import (
    ConnectorInvocation,
    ConnectorInvocationDenied,
)
from umbod.mcp.connectors.native import ApprovalCallerBinding, ApprovalStateCodec
from umbod.mcp.connectors.native.approval_principal import ApprovalActorIdentity


def _caller(user_id: str) -> ApprovalCallerBinding:
    return ApprovalCallerBinding(
        identity=ApprovalActorIdentity(agent_client_id="", authenticated_user_id=user_id)
    )


def _invocation(arguments: Mapping[str, object] | None = None) -> ConnectorInvocation:
    return ConnectorInvocation.create(
        connector_kind="openapi",
        connector_id="payments",
        operation_name="create_payment",
        public_tool_name="payments_create_payment",
        arguments={"amount": 10} if arguments is None else arguments,
    )


def test_invocation_baselines_have_separate_argument_mappings() -> None:
    first = _invocation()
    second = _invocation()

    assert first.arguments == second.arguments == {"amount": 10}
    assert first.arguments is not second.arguments


def test_invocation_snapshots_explicit_arguments() -> None:
    details = {"amount": 10}
    arguments: dict[str, object] = {"details": details}
    invocation = _invocation(arguments)
    details["amount"] = 99
    arguments["extra"] = True

    assert invocation.arguments == {"details": {"amount": 10}}


def test_invocation_preserves_empty_arguments() -> None:
    assert _invocation({}).arguments == {}


def test_codec_round_trips_bound_approval_state() -> None:
    codec = ApprovalStateCodec(clock=lambda: 1000.0, random_token=lambda: "nonce", ttl_seconds=300)

    token = codec.mint(_invocation(), 4, _caller("user-1"))

    assert codec.verify(
        token, _invocation(), 4, _caller("user-1")
    ) == {"nonce": "nonce", "expires_at": 1300}


@pytest.mark.parametrize(
    ("invocation", "revision", "principal"),
    [
        (_invocation({"amount": 11}), 4, _caller("user-1")),
        (_invocation({}), 4, _caller("user-1")),
        (_invocation(), 5, _caller("user-1")),
        (_invocation(), 4, _caller("user-2")),
    ],
)
def test_codec_rejects_changed_binding(
    invocation: ConnectorInvocation,
    revision: int,
    principal: ApprovalCallerBinding,
) -> None:
    codec = ApprovalStateCodec(clock=lambda: 1000.0, random_token=lambda: "nonce", ttl_seconds=300)
    token = codec.mint(_invocation(), 4, _caller("user-1"))

    with pytest.raises(ConnectorInvocationDenied, match="state invalid"):
        codec.verify(token, invocation, revision, principal)


def test_codec_rejects_expired_state() -> None:
    current_time = 1000.0
    codec = ApprovalStateCodec(clock=lambda: current_time, random_token=lambda: "nonce", ttl_seconds=300)
    token = codec.mint(_invocation(), 4, _caller("user-1"))
    current_time = 1301.0

    with pytest.raises(ConnectorInvocationDenied, match="state expired"):
        codec.verify(token, _invocation(), 4, _caller("user-1"))
