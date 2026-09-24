import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.server.context import Context, _current_context
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from mcp.types import ElicitResult

from umbod.core.invocation import InMemoryApprovalNonceStore
from umbod.core.invocation import (
    AskInvocationDecision,
    ConnectorInvocation,
    ConnectorInvocationDenied,
    DirectInvocationDecision,
)
from umbod.mcp.connectors import (
    ApprovalStateCodec,
    CurrentInvocationApprovalPrincipalProvider,
    McpConnectorInvocationApprovalPolicy,
    ModernConnectorApprovalRequired,
)
from umbod.mcp.logging import (
    McpInvocationActor,
    McpInvocationContext,
    McpInvocationCorrelation,
    set_mcp_invocation_context,
)


class FixedPolicy:
    def __init__(self, decision: DirectInvocationDecision | AskInvocationDecision) -> None:
        self.decision = decision

    async def evaluate(
        self, invocation: ConnectorInvocation
    ) -> DirectInvocationDecision | AskInvocationDecision:
        return self.decision


class ApprovalContext(Context):
    def __init__(self, *, modern: bool) -> None:
        super().__init__(FastMCP("approval-runtime-test"))
        self.modern = modern
        self.legacy_response: Any = None
        self.elicitations: list[tuple[str, type[bool]]] = []

    def _is_modern_protocol(self) -> bool:
        return self.modern

    async def elicit(self, message: str, response_type: type[bool], **kwargs: Any) -> Any:
        self.elicitations.append((message, response_type))
        if isinstance(self.legacy_response, BaseException):
            raise self.legacy_response
        return self.legacy_response


def _invocation(arguments: dict[str, Any] | None = None) -> ConnectorInvocation:
    return ConnectorInvocation.create(
        connector_kind="native",
        connector_id="secret-connector",
        operation_name="send",
        public_tool_name="connector_send",
        arguments=arguments or {"token": "credential-canary", "message": "argument-canary"},
    )


def _identity(user_id: str = "user-1") -> None:
    _identity_with_session(user_id, "session-1")


def _identity_with_session(user_id: str, session_id: str) -> None:
    set_mcp_invocation_context(
        McpInvocationContext(
            actor=McpInvocationActor(authenticated_user_id=user_id, session_id=session_id),
            correlation=McpInvocationCorrelation(trace_id="trace-1"),
            server_name="test",
        )
    )


async def _with_context(
    context: ApprovalContext, operation: Callable[[], Awaitable[Any]]
) -> Any:
    token = _current_context.set(context)
    try:
        return await operation()
    finally:
        _current_context.reset(token)


def _approval_codec(clock: Callable[[], float]) -> ApprovalStateCodec:
    return ApprovalStateCodec(
        clock=clock,
        random_token=lambda: "approval-nonce",
        ttl_seconds=300,
    )


@pytest.mark.asyncio
async def test_stored_direct_decision_does_not_elicit() -> None:
    _identity()
    context = ApprovalContext(modern=False)
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(DirectInvocationDecision()),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: 1000.0),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )

    decision = await _with_context(context, lambda: policy.evaluate(_invocation()))

    assert isinstance(decision, DirectInvocationDecision)
    assert context.elicitations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "accepted"),
    [
        (AcceptedElicitation(data=True), True),
        (DeclinedElicitation(), False),
        (CancelledElicitation(), False),
        (RuntimeError("elicitation unsupported"), False),
    ],
)
async def test_legacy_ask_accepts_only_explicit_true(
    response: AcceptedElicitation[bool] | DeclinedElicitation | CancelledElicitation | RuntimeError,
    accepted: bool,
) -> None:
    _identity()
    context = ApprovalContext(modern=False)
    context.legacy_response = response
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(4)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: 1000.0),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )

    if accepted:
        decision = await _with_context(context, lambda: policy.evaluate(_invocation()))
        assert isinstance(decision, DirectInvocationDecision)
    else:
        with pytest.raises((ConnectorInvocationDenied, RuntimeError)):
            await _with_context(context, lambda: policy.evaluate(_invocation()))
    assert len(context.elicitations) == 1


@pytest.mark.asyncio
async def test_modern_initial_result_uses_actual_mcp_wire_models_without_sensitive_values() -> None:
    _identity()
    context = ApprovalContext(modern=True)
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(7)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: 1000.0),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )

    with pytest.raises(ModernConnectorApprovalRequired) as raised:
        await _with_context(context, lambda: policy.evaluate(_invocation()))

    wire = raised.value.result.input_required.model_dump(by_alias=True, mode="json")
    serialized = json.dumps(wire)
    assert wire["inputRequests"]["connector_approval"]["method"] == "elicitation/create"
    assert wire["inputRequests"]["connector_approval"]["params"]["requestedSchema"]["required"] == [
        "value"
    ]
    assert "requestState" in wire
    assert "argument-canary" not in serialized
    assert "credential-canary" not in serialized


@pytest.mark.asyncio
async def test_modern_acceptance_consumes_state_once_at_five_minute_boundary() -> None:
    _identity()
    now = [1000.0]
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(7)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: now[0]),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )
    initial = ApprovalContext(modern=True)
    with pytest.raises(ModernConnectorApprovalRequired) as raised:
        await _with_context(initial, lambda: policy.evaluate(_invocation()))
    state = raised.value.result.input_required.request_state
    resumed = ApprovalContext(modern=True)
    resumed._task_request_state = state
    resumed._task_input_responses = {
        "connector_approval": ElicitResult(action="accept", content={"value": True})
    }
    now[0] = 1300.0
    _identity_with_session("user-1", "session-2")

    decision = await _with_context(resumed, lambda: policy.evaluate(_invocation()))

    assert isinstance(decision, DirectInvocationDecision)
    with pytest.raises(ConnectorInvocationDenied, match="already consumed"):
        await _with_context(resumed, lambda: policy.evaluate(_invocation()))


@pytest.mark.asyncio
async def test_modern_concurrent_replay_has_exactly_one_winner() -> None:
    _identity()
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(2)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: 1000.0),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )
    initial = ApprovalContext(modern=True)
    with pytest.raises(ModernConnectorApprovalRequired) as raised:
        await _with_context(initial, lambda: policy.evaluate(_invocation()))
    state = raised.value.result.input_required.request_state

    async def resume() -> bool:
        context = ApprovalContext(modern=True)
        context._task_request_state = state
        context._task_input_responses = {
            "connector_approval": ElicitResult(action="accept", content={"value": True})
        }
        try:
            await _with_context(context, lambda: policy.evaluate(_invocation()))
            return True
        except ConnectorInvocationDenied:
            return False

    assert sorted(await asyncio.gather(resume(), resume())) == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["arguments", "principal", "revision", "expired"])
async def test_modern_resume_rejects_changed_or_expired_approval(mutation: str) -> None:
    _identity()
    now = [1000.0]
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(3)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: now[0]),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )
    initial = ApprovalContext(modern=True)
    with pytest.raises(ModernConnectorApprovalRequired) as raised:
        await _with_context(initial, lambda: policy.evaluate(_invocation()))
    state = raised.value.result.input_required.request_state
    resumed = ApprovalContext(modern=True)
    resumed._task_request_state = state
    resumed._task_input_responses = {
        "connector_approval": ElicitResult(action="accept", content={"value": True})
    }
    invocation = _invocation({"message": "changed"}) if mutation == "arguments" else _invocation()
    if mutation == "principal":
        _identity("user-2")
    if mutation == "revision":
        policy._policy = FixedPolicy(AskInvocationDecision(4))
    if mutation == "expired":
        now[0] = 1300.0001

    with pytest.raises(ConnectorInvocationDenied):
        await _with_context(resumed, lambda: policy.evaluate(invocation))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "responses"),
    [("state", None), (None, {"connector_approval": ElicitResult(action="accept", content={"value": True})})],
)
async def test_modern_resume_rejects_malformed_state_response_pair(
    state: str | None, responses: dict[str, ElicitResult] | None
) -> None:
    _identity()
    context = ApprovalContext(modern=True)
    context._task_request_state = state
    context._task_input_responses = responses
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(1)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: 1000.0),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )

    with pytest.raises(ConnectorInvocationDenied, match="malformed"):
        await _with_context(context, lambda: policy.evaluate(_invocation()))


@pytest.mark.asyncio
async def test_modern_codemode_fails_closed_before_side_effect() -> None:
    _identity()
    context = ApprovalContext(modern=True)
    policy = McpConnectorInvocationApprovalPolicy(
        FixedPolicy(AskInvocationDecision(1)),
        nonce_store=InMemoryApprovalNonceStore(),
        state_codec=_approval_codec(lambda: 1000.0),
        principal_provider=CurrentInvocationApprovalPrincipalProvider(),
    )
    policy._is_codemode_request = lambda current: True

    with pytest.raises(ConnectorInvocationDenied, match="unsupported"):
        await _with_context(context, lambda: policy.evaluate(_invocation()))
