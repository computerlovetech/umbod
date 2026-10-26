import asyncio

import pytest

from umbod.core.capabilities import CapabilityIdentity
from umbod.core.invocation.failure_evidence import InvocationFailureOrigin
from umbod.core.invocation.tools.execution import ToolExecutionFailed, ToolExecutionInterceptor, ToolExecutionRequest, ToolExecutionSucceeded
from umbod.core.signals import InMemorySignalFailureHandler
from umbod.mcp.signals import McpSignals, McpToolInvocationCompleted, McpToolInvocationFailed
from umbod.mcp.signals.execution import ConnectorInvocationSignalInterceptor


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
