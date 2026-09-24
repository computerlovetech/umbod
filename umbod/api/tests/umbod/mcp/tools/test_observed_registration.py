import asyncio

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError
from fastmcp.tools import FunctionTool, ToolResult

from umbod.mcp.logging import (
    McpInvocationActor,
    McpInvocationContext,
    McpInvocationCorrelation,
    McpToolInvocationCompleted,
    McpToolInvocationFailureCategory,
    McpToolInvocationFailed,
    set_mcp_invocation_context,
)
from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.invocation import McpToolInvocationObserver


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[McpToolInvocationCompleted] = []

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        self.events.append(event)


class RecordingMetrics:
    def __init__(self) -> None:
        self.invocations: list[CompletedToolInvocation] = []

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.invocations.append(invocation)


class FailingLogger:
    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        raise RuntimeError("failed")


class FailingMetrics:
    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        raise RuntimeError("failed")


class RaisingObserver(McpToolInvocationObserver):
    def __init__(self, failing_method: str) -> None:
        super().__init__(RecordingLogger(), RecordingMetrics())
        self._failing_method = failing_method

    def start(self, identity: Any) -> Any:
        if self._failing_method == "start":
            raise RuntimeError("failed")
        return super().start(identity)

    def succeeded(self, lifecycle: Any) -> None:
        if self._failing_method == "succeeded":
            raise RuntimeError("failed")
        super().succeeded(lifecycle)

    def failed(self, lifecycle: Any, category: McpToolInvocationFailureCategory) -> None:
        if self._failing_method == "failed":
            raise RuntimeError("failed")
        super().failed(lifecycle, category)


def _registered_tool(
    fn: Callable[..., Any],
    observer: McpToolInvocationObserver,
    auth: Callable[[Any], bool] | None = None,
) -> Any:
    registrar = McpObservedToolRegistrar(FastMCP("test"), observer)
    return registrar.register(fn, name="internal_tool", description="Internal tool.", auth=auth)


def _set_invocation_context() -> None:
    set_mcp_invocation_context(
        McpInvocationContext(
            actor=McpInvocationActor(authenticated_user_id="user", agent_client_id="agent"),
            correlation=McpInvocationCorrelation(trace_id="trace", span_id="span"),
            server_name="test",
        )
    )


def _assert_internal_completion(event: McpToolInvocationCompleted) -> None:
    assert event.started.tool.tool_name == "internal_tool"
    assert event.started.tool.connector_id is None
    assert event.started.tool.connector_name is None
    assert event.started.tool.operation_name is None
    assert event.started.actor.authenticated_user_id == "user"
    assert event.started.correlation == McpInvocationCorrelation(trace_id="trace", span_id="span")
    assert event.duration_ms == 125.0


@pytest.mark.asyncio
async def test_success_records_internal_identity_context_duration_and_metric_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    metrics = RecordingMetrics()
    _set_invocation_context()
    monkeypatch.setattr(
        "umbod.mcp.tools.invocation.lifecycle.McpToolInvocationLifecycle._duration_ms",
        lambda self: 125.0,
    )

    async def invoke(value: int) -> dict[str, int]:
        return {"value": value}

    result = await _registered_tool(invoke, McpToolInvocationObserver(logger, metrics)).run({"value": 4})

    assert result.structured_content == {"value": 4}
    assert len(logger.events) == 1
    _assert_internal_completion(logger.events[0])
    assert metrics.invocations == [
        CompletedToolInvocation(
            connector_name="internal",
            tool_name="internal_tool",
            outcome=InvocationOutcome.SUCCESS,
            duration_seconds=0.125,
        )
    ]


def test_registration_preserves_callable_schemas_description_and_auth() -> None:
    def authorization(_context: Any) -> bool:
        return True

    def invoke(value: int) -> dict[str, int]:
        return {"value": value}

    expected = FunctionTool.from_function(
        invoke,
        name="internal_tool",
        description="Internal tool.",
        auth=authorization,
    )
    actual = _registered_tool(invoke, McpToolInvocationObserver(RecordingLogger(), RecordingMetrics()), authorization)

    assert actual.name == expected.name
    assert actual.description == expected.description
    assert actual.parameters == expected.parameters
    assert actual.output_schema == expected.output_schema
    assert actual.auth == expected.auth


@pytest.mark.asyncio
async def test_invalid_arguments_record_validation_without_entering_callable() -> None:
    entered = False
    logger = RecordingLogger()

    async def invoke(value: int) -> int:
        nonlocal entered
        entered = True
        return value

    with pytest.raises(ValidationError):
        await _registered_tool(invoke, McpToolInvocationObserver(logger, RecordingMetrics())).run({"value": "invalid"})

    assert entered is False
    assert len(logger.events) == 1
    assert isinstance(logger.events[0], McpToolInvocationFailed)
    assert logger.events[0].failure_category == McpToolInvocationFailureCategory.VALIDATION


@pytest.mark.asyncio
async def test_returned_error_is_returned_unchanged_and_recorded_as_failure() -> None:
    logger = RecordingLogger()
    returned = ToolResult(content=[], is_error=True)

    async def invoke() -> ToolResult:
        return returned

    result = await _registered_tool(invoke, McpToolInvocationObserver(logger, RecordingMetrics())).run({})

    assert result is returned
    assert isinstance(logger.events[0], McpToolInvocationFailed)
    assert logger.events[0].failure_category == McpToolInvocationFailureCategory.UNEXPECTED_ERROR


@pytest.mark.asyncio
async def test_original_exception_identity_is_preserved() -> None:
    failure = RuntimeError("domain failure")
    logger = RecordingLogger()

    async def invoke() -> None:
        raise failure

    with pytest.raises(RuntimeError) as raised:
        await _registered_tool(invoke, McpToolInvocationObserver(logger, RecordingMetrics())).run({})

    assert raised.value is failure
    assert isinstance(logger.events[0], McpToolInvocationFailed)


@pytest.mark.asyncio
async def test_cancellation_emits_no_completion() -> None:
    logger = RecordingLogger()

    async def invoke() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _registered_tool(invoke, McpToolInvocationObserver(logger, RecordingMetrics())).run({})

    assert logger.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_method", ["start", "succeeded"])
async def test_observer_failure_does_not_change_success_result(failing_method: str) -> None:
    async def invoke() -> str:
        return "ok"

    result = await _registered_tool(invoke, RaisingObserver(failing_method)).run({})

    assert result.structured_content == {"result": "ok"}


@pytest.mark.asyncio
async def test_observer_failure_does_not_replace_original_exception() -> None:
    failure = RuntimeError("domain failure")

    async def invoke() -> None:
        raise failure

    with pytest.raises(RuntimeError) as raised:
        await _registered_tool(invoke, RaisingObserver("failed")).run({})

    assert raised.value is failure


@pytest.mark.asyncio
async def test_logger_failure_still_records_metric_and_preserves_result() -> None:
    metrics = RecordingMetrics()

    async def invoke() -> str:
        return "ok"

    result = await _registered_tool(invoke, McpToolInvocationObserver(FailingLogger(), metrics)).run({})

    assert result.structured_content == {"result": "ok"}
    assert len(metrics.invocations) == 1


@pytest.mark.asyncio
async def test_metrics_failure_preserves_result_and_log() -> None:
    logger = RecordingLogger()

    async def invoke() -> str:
        return "ok"

    result = await _registered_tool(invoke, McpToolInvocationObserver(logger, FailingMetrics())).run({})

    assert result.structured_content == {"result": "ok"}
    assert len(logger.events) == 1
