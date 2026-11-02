from __future__ import annotations

import json

import pytest

from tests.support.application_failures import CapturingApplicationFailures
from umbod.logging import create_application_failure_signal
from umbod.logging import OpenTelemetryJsonFormatter

from umbod.mcp.logging import (
    McpAuditActivityType,
    McpAuthenticatedAuditActor,
    McpAuditClientMetadata,
    McpAuditCorrelation,
    McpAuditEvent,
    McpAuditFailureCategory,
    McpAuditIdentity,
    McpAuditOutcome,
    McpAuditRecorder,
)
from umbod.mcp.signals import McpToolIdentity
from umbod.mcp.logging.audit import McpAuditFailure
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class FailingSink:
    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        raise RuntimeError("secret-canary")


def _identity() -> McpAuditIdentity:
    return McpAuditIdentity(
        actor=McpAuthenticatedAuditActor("user@example.com"),
        client=McpAuditClientMetadata({"client_id": "claude-code", "session_id": "session-1"}),
    )


def _correlation() -> McpAuditCorrelation:
    return McpAuditCorrelation(trace_id="trace-1", span_id=None)


def test_record_client_connection_emits_server_scoped_success_event() -> None:
    sink = RecordingSink()
    recorder = McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal())

    recorder.record_client_connection(_identity(), _correlation())

    event = sink.events[0]
    assert event.activity_type == McpAuditActivityType.CLIENT_CONNECTION
    assert event.outcome == McpAuditOutcome.SUCCESS
    assert event.failure_category is None
    assert event.target.server_name == "umbod"
    assert event.target.tool_name is None
    assert event.correlation.trace_id == "trace-1"


def test_record_tool_discovery_emits_server_scoped_success_event() -> None:
    sink = RecordingSink()
    recorder = McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal())

    recorder.record_tool_discovery(_identity(), _correlation())

    event = sink.events[0]
    assert event.activity_type == McpAuditActivityType.TOOL_DISCOVERY
    assert event.outcome == McpAuditOutcome.SUCCESS
    assert event.target.tool_name is None


def test_record_tool_invocation_denied_marks_authorization_failure() -> None:
    sink = RecordingSink()
    recorder = McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal())
    target = recorder.tool_target(
        McpToolIdentity(
            tool_name="slack_post",
            connector_id="slack",
            operation_name="post",
            connector_name="Slack",
        )
    )

    recorder.record_tool_invocation_denied(_identity(), target, _correlation())

    event = sink.events[0]
    assert event.activity_type == McpAuditActivityType.TOOL_INVOCATION
    assert event.outcome == McpAuditOutcome.DENIED
    assert event.failure_category == McpAuditFailureCategory.AUTHORIZATION
    assert event.target.tool_name == "slack_post"
    assert event.target.connector_id == "slack"
    assert event.target.connector_name == "Slack"
    record = StructuredMcpAuditFormatter().format_mcp_activity(event)
    assert record.attributes["mcp.connector.name"] == "Slack"


def test_record_tool_invocation_uses_provided_outcome_and_timestamp() -> None:
    sink = RecordingSink()
    recorder = McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal())
    target = recorder.tool_target(McpToolIdentity("slack_post", "slack", "post"))

    recorder.record_tool_invocation(
        _identity(),
        target,
        McpAuditFailure(McpAuditFailureCategory.CONNECTOR_ERROR),
        _correlation(),
        123,
    )

    event = sink.events[0]
    assert event.outcome == McpAuditOutcome.FAILURE
    assert event.failure_category == McpAuditFailureCategory.CONNECTOR_ERROR
    assert event.occurred_at_unix_nano == 123
    assert event.actor.authenticated_user_id == "user@example.com"


def test_record_publishes_sink_failure_without_logging(caplog: pytest.LogCaptureFixture) -> None:
    failures = CapturingApplicationFailures()
    recorder = McpAuditRecorder(FailingSink(), "umbod", application_failures=failures)

    recorder.record_client_connection(_identity(), McpAuditCorrelation("a" * 32, None))

    assert caplog.records == []
    assert len(failures.events) == 1
    event = failures.events[0]
    assert event.correlation.trace_id == "a" * 32
    assert event.correlation.span_id is None
    assert dict(event.attributes)["reason"] == "sink_failed"
    assert "secret-canary" not in event.model_dump_json()


def test_record_swallows_sink_failure(caplog: pytest.LogCaptureFixture) -> None:
    recorder = McpAuditRecorder(FailingSink(), "umbod", application_failures=create_application_failure_signal())

    recorder.record_client_connection(_identity(), McpAuditCorrelation("a" * 32, "b" * 16))

    assert len(caplog.records) == 1
    serialized = OpenTelemetryJsonFormatter("test").format(caplog.records[0])
    payload = json.loads(serialized)
    assert "secret-canary" not in serialized
    assert payload["trace_id"] == "a" * 32
    assert payload["span_id"] == "b" * 16
    assert payload["attributes"]["exception.type"] == "RuntimeError"
    assert payload["attributes"]["reason"] == "sink_failed"
    assert "record_mcp_activity" in payload["attributes"]["exception.stacktrace"]
