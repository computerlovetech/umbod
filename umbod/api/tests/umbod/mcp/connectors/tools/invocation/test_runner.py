from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastmcp.tools import ToolResult

from umbod.core.invocation import (
    ConnectorInvocation,
    ConnectorInvocationDenied,
    ConnectorInvocationPolicy,
    PermitAllConnectorInvocationPolicy,
)
from umbod.core.invocation.tools.execution import create_tool_execution_pipeline
from umbod.mcp.connectors.tools.invocation.errors import (
    ConnectorToolErrorFormatter,
    ConnectorToolFailureResult,
)
from umbod.mcp.connectors.tools.invocation.runner import ConnectorToolInvocationRunner
from umbod.mcp.connectors.tools.invocation.telemetry import (
    ConnectorTelemetryInterceptor,
)
from umbod.mcp.metrics import (
    CompletedToolInvocation,
    InvocationOutcome,
    McpMetricsRecorder,
)
from umbod.mcp.logging import (
    McpAuditActivityType,
    McpAuditEvent,
    McpAuditOutcome,
    McpAuditRecorder,
    McpToolInvocationFailureCategory,
    McpToolInvocationOutcome,
    create_default_connector_tool_invocation_logger,
)
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink


@dataclass
class ConnectorToolMapping:
    connector_id: str
    operation_name: str
    description: str
    operation: Callable[..., dict[str, Any]]


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class RecordingMetricsRecorder:
    def __init__(self) -> None:
        self.invocations: list[CompletedToolInvocation] = []

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.invocations.append(invocation)


class FailingMetricsRecorder:
    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        raise RuntimeError("metrics failed")


class RecordingInvocationPolicy:
    def __init__(self, events: list[str], failure: BaseException | None = None) -> None:
        self.events = events
        self.failure = failure
        self.invocations: list[ConnectorInvocation] = []

    async def evaluate(self, invocation: ConnectorInvocation) -> None:
        self.events.append("policy")
        self.invocations.append(invocation)
        if self.failure is not None:
            raise self.failure


class FailingInvocationLogSink:
    def record_invocation_completed(self, event: object) -> None:
        raise RuntimeError("sink failed")


@dataclass(frozen=True)
class RunnerOptions:
    metrics_recorder: McpMetricsRecorder | None
    connector_name: str


def _mapping(operation: Callable[..., dict[str, Any]]) -> ConnectorToolMapping:
    return ConnectorToolMapping(
        connector_id="slack",
        operation_name="search_messages",
        description="Search Slack messages.",
        operation=operation,
    )


def _runner(
    mapping: ConnectorToolMapping,
    invocation_log_sink: InMemoryMcpToolInvocationLogSink | FailingInvocationLogSink,
    audit_sink: RecordingAuditSink,
    options: RunnerOptions = RunnerOptions(None, "Slack"),
    invocation_policy: ConnectorInvocationPolicy = PermitAllConnectorInvocationPolicy(),
) -> ConnectorToolInvocationRunner:
    telemetry = ConnectorTelemetryInterceptor(
        connector_name=options.connector_name,
        tool_invocation_logger=create_default_connector_tool_invocation_logger(
            invocation_log_sink,
            McpAuditRecorder(audit_sink, "test"),
        ),
        metrics_recorder=options.metrics_recorder or RecordingMetricsRecorder(),
        result_is_error=lambda result: False,
    )
    return ConnectorToolInvocationRunner(
        mapping=mapping,
        error_formatter=ConnectorToolErrorFormatter(),
        execution_pipeline=create_tool_execution_pipeline(
            invocation_policy,
            (telemetry,),
        ),
    )


@pytest.mark.asyncio
async def test_permitted_native_invocation_evaluates_canonical_context_before_one_operation() -> (
    None
):
    events: list[str] = []
    policy = RecordingInvocationPolicy(events)

    def operation(query: str, limit: int = 10) -> dict[str, Any]:
        events.append("operation")
        return {"query": query, "limit": limit}

    invoker = _runner(
        _mapping(operation),
        InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()),
        RecordingAuditSink(),
        invocation_policy=policy,
    )

    result = await invoker.invoke({"query": "release", "limit": 3})

    assert result.structured_content == {"query": "release", "limit": 3}
    assert events == ["policy", "operation"]
    assert policy.invocations == [
        ConnectorInvocation.create(
            connector_kind="native",
            connector_id="slack",
            operation_name="search_messages",
            public_tool_name="slack_search_messages",
            arguments={"query": "release", "limit": 3},
        )
    ]


@pytest.mark.asyncio
async def test_denied_native_invocation_records_failure_without_calling_operation() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events, ConnectorInvocationDenied("private rationale"))
    metrics = RecordingMetricsRecorder()
    invoker = _runner(
        _mapping(lambda query: events.append("operation") or {"query": query}),
        InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()),
        RecordingAuditSink(),
        RunnerOptions(metrics, "Slack"),
        policy,
    )

    result = await invoker.invoke({"query": "release"})

    assert isinstance(result, ConnectorToolFailureResult)
    assert "private rationale" not in result.content[0].text
    assert events == ["policy"]
    assert len(policy.invocations) == 1
    assert [item.outcome for item in metrics.invocations] == [InvocationOutcome.FAILURE]


@pytest.mark.asyncio
async def test_unexpected_native_policy_failure_hides_canary_without_calling_operation() -> None:
    canary = "policy-canary-secret"
    events: list[str] = []
    policy = RecordingInvocationPolicy(events, RuntimeError(canary))
    invoker = _runner(
        _mapping(lambda: events.append("operation") or {"ok": True}),
        InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()),
        RecordingAuditSink(),
        invocation_policy=policy,
    )

    result = await invoker.invoke({})

    assert isinstance(result, ConnectorToolFailureResult)
    assert canary not in result.content[0].text
    assert events == ["policy"]


@pytest.mark.asyncio
async def test_native_policy_cancellation_propagates_without_calling_operation() -> None:
    events: list[str] = []
    policy = RecordingInvocationPolicy(events, asyncio.CancelledError())
    invoker = _runner(
        _mapping(lambda: events.append("operation") or {"ok": True}),
        InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()),
        RecordingAuditSink(),
        invocation_policy=policy,
    )

    with pytest.raises(asyncio.CancelledError):
        await invoker.invoke({})

    assert events == ["policy"]


@pytest.mark.asyncio
async def test_invoke_success_records_invocation_and_audit_logs() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    invoker = _runner(_mapping(lambda: {"ok": True}), invocation_sink, audit_sink)

    result = await invoker.invoke({})

    assert isinstance(result, ToolResult)
    assert result.structured_content == {"ok": True}
    assert json.loads(result.content[0].text) == {"ok": True}
    invocation_record = invocation_sink.invocation_records()[0]
    assert invocation_record.attributes["mcp.tool.name"] == "slack_search_messages"
    assert invocation_record.attributes["mcp.connector.name"] == "Slack"
    assert (
        invocation_record.attributes["mcp.invocation.outcome"] == McpToolInvocationOutcome.SUCCESS
    )
    audit_event = audit_sink.events[0]
    assert audit_event.activity_type == McpAuditActivityType.TOOL_INVOCATION
    assert audit_event.outcome == McpAuditOutcome.SUCCESS
    assert audit_event.target.tool_name == "slack_search_messages"
    assert audit_event.target.connector_name == "Slack"


@pytest.mark.asyncio
async def test_invoke_uses_connector_id_name_fallback_supplied_by_boundary() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    invoker = _runner(
        _mapping(lambda: {"ok": True}),
        invocation_sink,
        RecordingAuditSink(),
        RunnerOptions(None, "slack"),
    )

    await invoker.invoke({})

    assert invocation_sink.invocation_records()[0].attributes["mcp.connector.name"] == "slack"


@pytest.mark.asyncio
async def test_invoke_connector_error_returns_failure_result_and_records_failure() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()

    def failing_operation() -> dict[str, Any]:
        raise ValueError("channel not found")

    invoker = _runner(_mapping(failing_operation), invocation_sink, audit_sink)

    result = await invoker.invoke({})

    assert isinstance(result, ConnectorToolFailureResult)
    assert "channel not found" in result.content[0].text
    invocation_record = invocation_sink.invocation_records()[0]
    assert (
        invocation_record.attributes["mcp.invocation.outcome"] == McpToolInvocationOutcome.FAILURE
    )
    assert (
        invocation_record.attributes["mcp.failure.category"]
        == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    )
    audit_event = audit_sink.events[0]
    assert audit_event.outcome == McpAuditOutcome.FAILURE


@pytest.mark.asyncio
async def test_success_records_metrics_with_external_identity_and_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "umbod.mcp.connectors.tools.invocation.lifecycle.ConnectorInvocationLifecycle._duration_ms",
        lambda self: 250.0,
    )
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    metrics_recorder = RecordingMetricsRecorder()
    invoker = _runner(
        _mapping(lambda: {"ok": True}),
        invocation_sink,
        audit_sink,
        RunnerOptions(metrics_recorder, "Slack"),
    )

    await invoker.invoke({})

    invocation = metrics_recorder.invocations[0]
    assert invocation.connector_name == "slack"
    assert invocation.tool_name == "slack_search_messages"
    assert invocation.outcome == InvocationOutcome.SUCCESS
    assert invocation.duration_seconds == 0.25


@pytest.mark.asyncio
async def test_failure_records_failure_metrics_once() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    audit_sink = RecordingAuditSink()
    metrics_recorder = RecordingMetricsRecorder()

    def failing_operation() -> dict[str, Any]:
        raise ValueError("channel not found")

    invoker = _runner(
        _mapping(failing_operation),
        invocation_sink,
        audit_sink,
        RunnerOptions(metrics_recorder, "Slack"),
    )

    result = await invoker.invoke({})

    assert isinstance(result, ConnectorToolFailureResult)
    assert len(metrics_recorder.invocations) == 1
    assert metrics_recorder.invocations[0].outcome == InvocationOutcome.FAILURE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation", [lambda: {"ok": True}, lambda: (_ for _ in ()).throw(ValueError("failed"))]
)
async def test_metrics_recorder_failure_preserves_tool_result(
    operation: Callable[..., dict[str, Any]],
) -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    invoker = _runner(
        _mapping(operation),
        invocation_sink,
        RecordingAuditSink(),
        RunnerOptions(FailingMetricsRecorder(), "Slack"),
    )

    result = await invoker.invoke({})

    assert isinstance(result, ToolResult)
    assert bool(isinstance(result, ConnectorToolFailureResult)) == (
        "ok" not in (result.structured_content or {})
    )


@pytest.mark.asyncio
async def test_result_predicate_failure_preserves_result_and_records_failure() -> None:
    invocation_sink = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    metrics = RecordingMetricsRecorder()

    def failing_predicate(_result: object) -> bool:
        raise RuntimeError("predicate failed")

    telemetry = ConnectorTelemetryInterceptor(
        connector_name="Slack",
        tool_invocation_logger=create_default_connector_tool_invocation_logger(
            invocation_sink,
            McpAuditRecorder(RecordingAuditSink(), "test"),
        ),
        metrics_recorder=metrics,
        result_is_error=failing_predicate,
    )
    invoker = ConnectorToolInvocationRunner(
        mapping=_mapping(lambda: {"ok": True}),
        error_formatter=ConnectorToolErrorFormatter(),
        execution_pipeline=create_tool_execution_pipeline(
            PermitAllConnectorInvocationPolicy(),
            (telemetry,),
        ),
    )

    result = await invoker.invoke({})

    assert result.structured_content == {"ok": True}
    assert invocation_sink.invocation_records()[0].attributes["mcp.failure.category"] == McpToolInvocationFailureCategory.CONNECTOR_ERROR
    assert metrics.invocations[0].outcome == InvocationOutcome.FAILURE


@pytest.mark.asyncio
async def test_invoke_swallows_invocation_logging_failures() -> None:
    audit_sink = RecordingAuditSink()
    invoker = _runner(_mapping(lambda: {"ok": True}), FailingInvocationLogSink(), audit_sink)

    result = await invoker.invoke({})

    assert result.structured_content == {"ok": True}
    assert len(audit_sink.events) == 1
