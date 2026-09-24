from collections.abc import Mapping

import pytest

from umbod.core.invocation import (
    ConnectorInvocation,
    ConnectorInvocationDenied,
)
from umbod.mcp.connectors import ApprovalStateCodec


def _invocation(arguments: Mapping[str, object] = {"amount": 10}) -> ConnectorInvocation:
    return ConnectorInvocation(
        connector_kind="openapi",
        connector_id="payments",
        operation_name="create_payment",
        public_tool_name="payments_create_payment",
        arguments=arguments,
    )


def test_codec_round_trips_bound_approval_state() -> None:
    codec = ApprovalStateCodec(clock=lambda: 1000.0, random_token=lambda: "nonce", ttl_seconds=300)

    token = codec.mint(_invocation(), 4, {"authenticated_user_id": "user-1"})

    assert codec.verify(
        token, _invocation(), 4, {"authenticated_user_id": "user-1"}
    ) == {"nonce": "nonce", "expires_at": 1300}


@pytest.mark.parametrize(
    ("invocation", "revision", "principal"),
    [
        (_invocation({"amount": 11}), 4, {"authenticated_user_id": "user-1"}),
        (_invocation(), 5, {"authenticated_user_id": "user-1"}),
        (_invocation(), 4, {"authenticated_user_id": "user-2"}),
    ],
)
def test_codec_rejects_changed_binding(
    invocation: ConnectorInvocation,
    revision: int,
    principal: Mapping[str, str],
) -> None:
    codec = ApprovalStateCodec(clock=lambda: 1000.0, random_token=lambda: "nonce", ttl_seconds=300)
    token = codec.mint(_invocation(), 4, {"authenticated_user_id": "user-1"})

    with pytest.raises(ConnectorInvocationDenied, match="state invalid"):
        codec.verify(token, invocation, revision, principal)


def test_codec_rejects_expired_state() -> None:
    current_time = 1000.0
    codec = ApprovalStateCodec(clock=lambda: current_time, random_token=lambda: "nonce", ttl_seconds=300)
    token = codec.mint(_invocation(), 4, {"authenticated_user_id": "user-1"})
    current_time = 1301.0

    with pytest.raises(ConnectorInvocationDenied, match="state expired"):
        codec.verify(token, _invocation(), 4, {"authenticated_user_id": "user-1"})
