import asyncio
import math
import socket

from unittest.mock import Mock

from collections.abc import Callable
from typing import Any, Optional

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.tools import FunctionTool, InputRequiredToolResult, ToolResult
from mcp.types import InputRequiredResult

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureEvidence,
    InvocationFailureOrigin,
    InvocationReturnedFailure,
)
from umbod.mcp.signals import (
    McpInvocationActor,
    McpInvocationContext,
    McpInvocationCorrelation,
    McpToolInvocationCompleted,
    McpToolInvocationFailureCategory,
    McpToolInvocationFailed,
    McpToolInvocationSucceeded,
    set_mcp_invocation_context,
)
from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome, InvocationScope
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle
from umbod.mcp.tools.errors import ToolAuthorizationDenied, ToolResponseContractError
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from tests.support.signals import InMemorySignalFailureHandler
from umbod.mcp.listeners.invocation_metrics import InvocationMetricsReceiver
from umbod.mcp.metrics import McpMetricsRecorder, ToolInvocationMetricIdentity
from umbod.mcp.signals import McpInvocationPublisher, McpSignals


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[McpToolInvocationCompleted] = []

    def __call__(self, event: McpToolInvocationCompleted) -> None:
        self.events.append(event)


class RecordingMetrics:
    def __init__(self) -> None:
        self.invocations: list[CompletedToolInvocation] = []

    def initialize_invocation(self, identity: ToolInvocationMetricIdentity) -> None:
        return None

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.invocations.append(invocation)


class FailingLogger:
    def __call__(self, event: McpToolInvocationCompleted) -> None:
        raise RuntimeError("failed")


class FailingMetrics:
    def initialize_invocation(self, identity: ToolInvocationMetricIdentity) -> None:
        return None

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        raise RuntimeError("failed")


def _test_signals(logger: Callable[[McpToolInvocationCompleted], None], metrics: McpMetricsRecorder) -> McpSignals:
    signals = McpSignals(InMemorySignalFailureHandler())
    signals.invocation_completed.connect("test.logger", logger)
    signals.invocation_completed.connect("test.metrics", InvocationMetricsReceiver(metrics))
    return signals


def _publisher(logger: Callable[[McpToolInvocationCompleted], None], metrics: McpMetricsRecorder) -> McpInvocationPublisher:
    return McpInvocationPublisher(_test_signals(logger, metrics))


class RaisingObserver(McpInvocationPublisher):
    def __init__(self, failing_method: str) -> None:
        super().__init__(_test_signals(RecordingLogger(), RecordingMetrics()))
        self._failing_method = failing_method

    def start(self, identity: Any) -> Any:
        if self._failing_method == "start":
            raise RuntimeError("failed")
        return super().start(identity)

    def succeeded(self, lifecycle: Any) -> None:
        if self._failing_method == "succeeded":
            raise RuntimeError("failed")
        super().succeeded(lifecycle)

    def failed(self, lifecycle: Any, category: McpToolInvocationFailureCategory, diagnostic: Optional[InvocationFailureDiagnostic] = None, evidence: Optional[InvocationFailureEvidence] = None) -> None:
        if self._failing_method == "failed":
            raise RuntimeError("failed")
        super().failed(lifecycle, category, diagnostic, evidence)


def _registered_tool(
    fn: Callable[..., Any],
    observer: McpInvocationPublisher,
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
    assert math.isfinite(event.duration_ms)
    assert event.duration_ms >= 0


@pytest.mark.asyncio
async def test_success_records_internal_identity_context_duration_and_metric_once() -> None:
    logger = RecordingLogger()
    metrics = RecordingMetrics()
    _set_invocation_context()

    async def invoke(value: int) -> dict[str, int]:
        return {"value": value}

    result = await _registered_tool(invoke, _publisher(logger, metrics)).run({"value": 4})

    assert result.structured_content == {"value": 4}
    assert len(logger.events) == 1
    _assert_internal_completion(logger.events[0])
    assert metrics.invocations == [
        CompletedToolInvocation(
            scope=InvocationScope.REQUEST,
            connector_name="internal",
            tool_name="internal_tool",
            outcome=InvocationOutcome.SUCCESS,
            duration_seconds=max(logger.events[0].duration_ms / 1000, 1e-12),
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
    actual = _registered_tool(invoke, _publisher(RecordingLogger(), RecordingMetrics()), authorization)

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
        await _registered_tool(invoke, _publisher(logger, RecordingMetrics())).run({"value": "invalid"})

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

    result = await _registered_tool(invoke, _publisher(logger, RecordingMetrics())).run({})

    assert result is returned
    assert len(logger.events) == 1
    assert isinstance(logger.events[0], McpToolInvocationFailed)
    assert logger.events[0].evidence == InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL)
    assert logger.events[0].failure_category == McpToolInvocationFailureCategory.UNEXPECTED_ERROR


@pytest.mark.asyncio
async def test_original_exception_identity_is_preserved() -> None:
    failure = RuntimeError("secret-domain-failure")
    logger = RecordingLogger()

    async def invoke() -> None:
        raise failure

    with pytest.raises(RuntimeError) as raised:
        await _registered_tool(invoke, _publisher(logger, RecordingMetrics())).run({})

    assert raised.value is failure
    assert len(logger.events) == 1
    assert isinstance(logger.events[0], McpToolInvocationFailed)
    evidence = logger.events[0].evidence
    assert isinstance(evidence, InvocationExceptionEvidence)
    assert evidence.origin == InvocationFailureOrigin.INTERNAL
    assert evidence.exception_type == "RuntimeError"
    assert "in invoke" in evidence.stacktrace
    assert "secret-domain-failure" not in evidence.stacktrace
    assert "raise failure" not in evidence.stacktrace


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type,category,severity", [
    (ToolAuthorizationDenied, McpToolInvocationFailureCategory.AUTHORIZATION, "WARNING"),
    (ToolError, McpToolInvocationFailureCategory.UNEXPECTED_ERROR, "ERROR"),
])
async def test_only_typed_authorization_denials_avoid_error_telemetry(
    failure_type: type[ToolError], category: McpToolInvocationFailureCategory, severity: str,
) -> None:
    failure = failure_type("filesystem_permission_denied: Filesystem access denied")
    logger = RecordingLogger()

    async def invoke() -> None:
        raise failure

    with pytest.raises(failure_type) as raised:
        await _registered_tool(invoke, _publisher(logger, RecordingMetrics())).run({})

    assert raised.value is failure
    assert len(logger.events) == 1
    event = logger.events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == category
    assert StructuredMcpToolInvocationLogFormatter().format_invocation_completed(event).severity_text == severity


@pytest.mark.asyncio
async def test_cancellation_emits_no_completion() -> None:
    logger = RecordingLogger()

    async def invoke() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _registered_tool(invoke, _publisher(logger, RecordingMetrics())).run({})

    assert logger.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_method", ["start", "succeeded"])
async def test_observer_failure_does_not_change_success_result(failing_method: str) -> None:
    async def invoke() -> str:
        return "ok"

    result = await _registered_tool(invoke, RaisingObserver(failing_method)).run({})

    assert result.structured_content == {"result": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize("startup_source", ["lifecycle", "publisher"])
@pytest.mark.parametrize("execution_outcome", ["success", "returned_failure", "exception"])
async def test_startup_failure_preserves_primary_outcome_without_fake_completion(
    startup_source: str, execution_outcome: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    metrics = RecordingMetrics()
    publisher = _publisher(logger, metrics)
    startup_target = McpToolInvocationLifecycle if startup_source == "lifecycle" else publisher
    monkeypatch.setattr(startup_target, "start", Mock(side_effect=RuntimeError("private-start-token")))
    succeeded = Mock(wraps=publisher.succeeded)
    failed = Mock(wraps=publisher.failed)
    monkeypatch.setattr(publisher, "succeeded", succeeded)
    monkeypatch.setattr(publisher, "failed", failed)
    returned = ToolResult(content=[], is_error=execution_outcome == "returned_failure")
    failure = RuntimeError("primary-failure")

    async def invoke() -> ToolResult:
        if execution_outcome == "exception":
            raise failure
        return returned

    tool = _registered_tool(invoke, publisher)
    if execution_outcome == "exception":
        with pytest.raises(RuntimeError) as raised:
            await tool.run({})
        assert raised.value is failure
    else:
        assert await tool.run({}) is returned

    completion = succeeded if execution_outcome == "success" else failed
    completion.assert_called_once()
    assert isinstance(completion.call_args.args[0], UnavailableToolInvocationLifecycle)
    assert logger.events == []
    assert metrics.invocations == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [RuntimeError, ToolAuthorizationDenied])
async def test_observer_failure_does_not_replace_original_exception(failure_type: type[Exception]) -> None:
    failure = failure_type("domain failure")

    async def invoke() -> None:
        raise failure

    with pytest.raises(failure_type) as raised:
        await _registered_tool(invoke, RaisingObserver("failed")).run({})

    assert raised.value is failure


@pytest.mark.asyncio
async def test_logger_failure_still_records_metric_and_preserves_result() -> None:
    metrics = RecordingMetrics()

    async def invoke() -> str:
        return "ok"

    result = await _registered_tool(invoke, _publisher(FailingLogger(), metrics)).run({})

    assert result.structured_content == {"result": "ok"}
    assert len(metrics.invocations) == 1


@pytest.mark.asyncio
async def test_metrics_failure_preserves_result_and_log() -> None:
    logger = RecordingLogger()

    async def invoke() -> str:
        return "ok"

    result = await _registered_tool(invoke, _publisher(logger, FailingMetrics())).run({})

    assert result.structured_content == {"result": "ok"}
    assert len(logger.events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_content", [{"value": "payload-secret-sentinel"}, None])
async def test_client_receives_safe_contract_error_after_mutation_without_success(
    structured_content: Optional[dict[str, Any]],
) -> None:
    logger = RecordingLogger()
    metrics = RecordingMetrics()
    mutations: list[str] = []
    mcp = FastMCP("test")

    async def invoke() -> ToolResult:
        mutations.append("completed")
        return ToolResult(content="content-secret-sentinel", structured_content=structured_content)

    tool = McpObservedToolRegistrar(mcp, _publisher(logger, metrics)).register(
        invoke, name="internal_tool", description="Internal tool.", auth=None,
    )
    tool.output_schema = {
        "type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"],
    }

    async with Client(mcp) as client:
        result = await client.call_tool("internal_tool", {}, raise_on_error=False)

    assert result.is_error is True
    assert result.structured_content is None
    assert result.content[0].text == str(ToolResponseContractError())
    assert mutations == ["completed"]
    assert len(logger.events) == 1
    event = logger.events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.failure_category == McpToolInvocationFailureCategory.UNEXPECTED_ERROR
    assert event.diagnostic == InvocationFailureDiagnostic(
        execution_mode="shared", stage="output", reason="invalid_output",
    )
    assert isinstance(event.evidence, InvocationExceptionEvidence)
    assert event.evidence.exception_type == "ToolResponseContractError"
    assert "payload-secret-sentinel" not in repr(event)
    assert "content-secret-sentinel" not in repr(event)
    assert "payload-secret-sentinel" not in repr(result)
    assert "content-secret-sentinel" not in repr(result)
    assert len(metrics.invocations) == 1
    assert metrics.invocations[0].outcome == InvocationOutcome.FAILURE


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", [
    {"type": "schema-secret-sentinel"},
    {"$ref": "https://schema-secret-sentinel.invalid/private-schema-path"},
])
async def test_invalid_or_remote_schema_fails_safely_without_network(
    schema: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    mcp = FastMCP("test")
    network_connect = Mock(side_effect=AssertionError("Network retrieval must not run"))
    network_lookup = Mock(side_effect=AssertionError("Network lookup must not run"))

    async def invoke() -> ToolResult:
        return ToolResult(structured_content={"value": "payload-secret-sentinel"})

    tool = McpObservedToolRegistrar(mcp, _publisher(logger, RecordingMetrics())).register(
        invoke, name="internal_tool", description="Internal tool.", auth=None,
    )
    tool.output_schema = schema

    async with Client(mcp) as client:
        with monkeypatch.context() as patch:
            patch.setattr(socket.socket, "connect", network_connect)
            patch.setattr(socket, "getaddrinfo", network_lookup)
            result = await client.call_tool("internal_tool", {}, raise_on_error=False)

    network_connect.assert_not_called()
    network_lookup.assert_not_called()
    assert result.is_error is True
    assert result.structured_content is None
    assert result.content[0].text == str(ToolResponseContractError())
    assert len(logger.events) == 1
    event = logger.events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.diagnostic == InvocationFailureDiagnostic(
        execution_mode="shared", stage="output", reason="invalid_output",
    )
    assert isinstance(event.evidence, InvocationExceptionEvidence)
    assert event.evidence.exception_type == "ToolResponseContractError"
    assert "schema-secret-sentinel" not in repr(event)
    assert "private-schema-path" not in repr(event)
    assert "payload-secret-sentinel" not in repr(event)
    assert "schema-secret-sentinel" not in repr(result)
    assert "private-schema-path" not in repr(result)
    assert "payload-secret-sentinel" not in repr(result)


@pytest.mark.asyncio
async def test_schema_mutation_invalidates_cached_contract() -> None:
    logger = RecordingLogger()

    async def invoke() -> ToolResult:
        return ToolResult(structured_content={"value": 4})

    tool = _registered_tool(invoke, _publisher(logger, RecordingMetrics()))
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}}
    tool.output_schema = schema
    result = await tool.run({})
    schema["properties"]["value"]["type"] = "string"

    with pytest.raises(ToolResponseContractError) as raised:
        await tool.run({})

    assert result.structured_content == {"value": 4}
    assert raised.value.__context__ is None
    assert len(logger.events) == 2
    assert isinstance(logger.events[0], McpToolInvocationSucceeded)
    assert isinstance(logger.events[1], McpToolInvocationFailed)


@pytest.mark.asyncio
async def test_client_valid_response_matches_schema_assigned_after_registration() -> None:
    logger = RecordingLogger()
    mcp = FastMCP("test")

    async def invoke() -> ToolResult:
        return ToolResult(structured_content={"value": 4})

    tool = McpObservedToolRegistrar(mcp, _publisher(logger, RecordingMetrics())).register(
        invoke, name="internal_tool", description="Internal tool.", auth=None,
    )
    tool.output_schema = {
        "type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"],
    }

    async with Client(mcp) as client:
        listed = await client.list_tools()
        result = await client.call_tool("internal_tool", {})

    assert listed[0].output_schema == tool.output_schema
    assert result.is_error is False
    assert result.structured_content == {"value": 4}
    assert len(logger.events) == 1
    assert isinstance(logger.events[0], McpToolInvocationSucceeded)


@pytest.mark.asyncio
async def test_returned_error_skips_output_contract_guard() -> None:
    logger = RecordingLogger()
    returned = ToolResult(content="expected failure", is_error=True)

    async def invoke() -> ToolResult:
        return returned

    tool = _registered_tool(invoke, _publisher(logger, RecordingMetrics()))
    tool.output_schema = {"type": "object", "required": ["value"]}
    result = await tool.run({})

    assert result is returned
    assert len(logger.events) == 1
    assert isinstance(logger.events[0], McpToolInvocationFailed)
    assert logger.events[0].diagnostic is None
    assert logger.events[0].evidence == InvocationReturnedFailure(InvocationFailureOrigin.INTERNAL)


@pytest.mark.asyncio
async def test_no_output_schema_accepts_unstructured_success() -> None:
    logger = RecordingLogger()
    returned = ToolResult(content="ok")

    async def invoke() -> ToolResult:
        return returned

    tool = _registered_tool(invoke, _publisher(logger, RecordingMetrics()))
    assert tool.output_schema is None
    result = await tool.run({})

    assert result is returned
    assert len(logger.events) == 1
    assert isinstance(logger.events[0], McpToolInvocationSucceeded)


@pytest.mark.asyncio
async def test_contract_failure_is_preserved_when_failure_observer_raises() -> None:
    async def invoke() -> ToolResult:
        return ToolResult(content="private content")

    tool = _registered_tool(invoke, RaisingObserver("failed"))
    tool.output_schema = {"type": "object"}

    with pytest.raises(ToolResponseContractError) as raised:
        await tool.run({})

    assert str(raised.value) == str(ToolResponseContractError())
    assert raised.value.__context__ is None


@pytest.mark.asyncio
async def test_input_required_skips_output_contract_guard_and_completion() -> None:
    logger = RecordingLogger()
    returned = InputRequiredToolResult(InputRequiredResult(request_state="pending"))

    async def invoke() -> ToolResult:
        return returned

    tool = _registered_tool(invoke, _publisher(logger, RecordingMetrics()))
    tool.output_schema = {"type": "object", "required": ["value"]}
    result = await tool.run({})

    assert result is returned
    assert logger.events == []


@pytest.mark.asyncio
async def test_contract_failure_receiver_isolation_preserves_failure_metric() -> None:
    metrics = RecordingMetrics()

    async def invoke() -> ToolResult:
        return ToolResult(content="private content")

    tool = _registered_tool(invoke, _publisher(FailingLogger(), metrics))
    tool.output_schema = {"type": "object"}

    with pytest.raises(ToolResponseContractError):
        await tool.run({})

    assert len(metrics.invocations) == 1
    assert metrics.invocations[0].outcome == InvocationOutcome.FAILURE
