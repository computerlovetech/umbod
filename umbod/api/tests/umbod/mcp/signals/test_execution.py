import asyncio
from unittest.mock import Mock

import pytest

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation.failure_evidence import InvocationFailureOrigin
from umbod.core.invocation.tools.execution import ToolExecutionFailed, ToolExecutionInterceptor, ToolExecutionOutcome, ToolExecutionRequest, ToolExecutionSucceeded
from tests.support.signals import InMemorySignalFailureHandler
from umbod.mcp.signals import McpSignals, McpToolInvocationCompleted, McpToolInvocationFailed
from umbod.mcp.signals.execution import ConnectorInvocationSignalInterceptor
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle


@pytest.fixture
def execution_request() -> ToolExecutionRequest:
    return ToolExecutionRequest(
        identity=CapabilityIdentity(connector_kind="openapi", connector_id="connector", capability_kind="tool", capability_key="operation"),
        public_tool_name="tool",
        arguments={},
    )


@pytest.mark.asyncio
async def test_returned_openapi_failure_has_origin_without_exception(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classifier(result: object) -> bool:
        return True

    interceptor: ToolExecutionInterceptor = ConnectorInvocationSignalInterceptor("name", signals, classifier)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.evidence is not None
    assert event.evidence.origin == InvocationFailureOrigin.OPENAPI


@pytest.mark.asyncio
async def test_result_classifier_exception_becomes_internal_failure_without_raising(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classify(result: object) -> bool:
        raise RuntimeError("secret")

    interceptor: ToolExecutionInterceptor = ConnectorInvocationSignalInterceptor("name", signals, classify)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.evidence is not None
    assert event.evidence.origin == InvocationFailureOrigin.INTERNAL


@pytest.mark.asyncio
async def test_cancellation_does_not_publish_completion(execution_request: ToolExecutionRequest) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)

    def classifier(result: object) -> bool:
        return False

    interceptor: ToolExecutionInterceptor = ConnectorInvocationSignalInterceptor("name", signals, classifier)
    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionFailed(asyncio.CancelledError()), state)
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [ToolExecutionSucceeded(object()), ToolExecutionFailed(RuntimeError("failed"))])
async def test_unavailable_lifecycle_does_not_publish_completion(
    execution_request: ToolExecutionRequest, outcome: ToolExecutionOutcome,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    classifier = Mock(return_value=False)
    interceptor = ConnectorInvocationSignalInterceptor("name", signals, classifier)

    await interceptor.after_tool_execution(execution_request, outcome, UnavailableToolInvocationLifecycle())

    assert events == []
    classifier.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, object(), "invalid"])
async def test_invalid_lifecycle_state_is_rejected(execution_request: ToolExecutionRequest, state: object) -> None:
    interceptor = ConnectorInvocationSignalInterceptor("name", McpSignals(InMemorySignalFailureHandler()), Mock())

    with pytest.raises(TypeError, match="Invalid connector invocation lifecycle state"):
        await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)


@pytest.mark.asyncio
async def test_start_failure_returns_unavailable_connector_state(
    execution_request: ToolExecutionRequest, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals = McpSignals(InMemorySignalFailureHandler())
    events: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", events.append)
    monkeypatch.setattr(McpToolInvocationLifecycle, "start", Mock(side_effect=RuntimeError("private-start-token")))
    interceptor = ConnectorInvocationSignalInterceptor("name", signals, Mock(return_value=False))

    state = await interceptor.before_tool_preparation(execution_request)
    await interceptor.after_tool_execution(execution_request, ToolExecutionSucceeded(object()), state)

    assert isinstance(state, UnavailableToolInvocationLifecycle)
    assert events == []
