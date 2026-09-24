from dataclasses import dataclass, replace

import pytest

from umbod.mcp.logging.invocation.event import (
    McpInteractionType,
    McpInvocationActor,
    McpToolIdentity,
    McpToolInvocationCompleted,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
    McpToolInvocationStarted,
    McpToolInvocationSucceeded,
)
from umbod.mcp.logging.invocation.formatting import (
    McpToolInvocationLogFormatter,
    StructuredLogRecord,
    StructuredMcpToolInvocationLogFormatter,
)
from umbod.mcp.logging.invocation.sink import (
    InMemoryMcpToolInvocationLogSink,
    McpToolInvocationLogReader,
    McpToolInvocationLogSink,
)


@dataclass(frozen=True)
class McpToolInvocationRequest:
    tool: McpToolIdentity
    actor: McpInvocationActor
    duration_ms: float


@dataclass(frozen=True)
class McpFailedToolInvocationRequest:
    invocation: McpToolInvocationRequest
    failure_category: McpToolInvocationFailureCategory


DEFAULT_ACTOR = McpInvocationActor(
    authenticated_user_id="user@example.com",
    agent_client_id="claude-code",
    session_id="session-123",
)


@dataclass(frozen=True)
class InMemoryMcpToolInvocationLogging:
    sink: McpToolInvocationLogSink
    formatter: McpToolInvocationLogFormatter
    reader: McpToolInvocationLogReader


class McpToolInvocationLoggingDsl:
    def __init__(self, logging: InMemoryMcpToolInvocationLogging) -> None:
        self._logging = logging

    def complete_successful_invocation(self, invocation: McpToolInvocationRequest) -> None:
        self._logging.sink.record_invocation_completed(_successful_invocation(invocation))

    def complete_failed_invocation(self, request: McpFailedToolInvocationRequest) -> None:
        self._logging.sink.record_invocation_completed(
            _failed_invocation(request.invocation, request.failure_category)
        )

    def invocation_logs(self) -> tuple[StructuredLogRecord, ...]:
        return self._logging.reader.invocation_records()

    def formatted_record_for(
        self,
        invocation: McpToolInvocationCompleted,
    ) -> StructuredLogRecord:
        return self._logging.formatter.format_invocation_completed(invocation)


@pytest.fixture
def mcp_invocation_logging() -> McpToolInvocationLoggingDsl:
    formatter = StructuredMcpToolInvocationLogFormatter()
    sink = InMemoryMcpToolInvocationLogSink(formatter)
    return McpToolInvocationLoggingDsl(
        InMemoryMcpToolInvocationLogging(
            sink=sink,
            formatter=formatter,
            reader=sink,
        )
    )


def test_successful_tool_invocation_is_logged(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_successful_invocation(
        _invocation_request("github_create_issue", "github", "create_issue")
    )

    record = _single_record(mcp_invocation_logging)

    assert record.attributes["mcp.interaction.type"] == "tool_invocation"
    assert record.attributes["mcp.tool.name"] == "github_create_issue"
    assert record.attributes["mcp.connector.id"] == "github"
    assert record.attributes["mcp.operation.name"] == "create_issue"
    assert record.attributes["enduser.id"] == "user@example.com"
    assert record.attributes["mcp.client.id"] == "claude-code"
    assert record.attributes["mcp.session.id"] == "session-123"
    assert record.attributes["mcp.invocation.outcome"] == "success"
    assert "mcp.invocation.duration_ms" in record.attributes


def test_logging_does_not_change_successful_tool_response(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_successful_invocation(
        _invocation_request("test_echo", "test", "echo")
    )

    assert len(mcp_invocation_logging.invocation_logs()) == 1


def test_invocation_is_logged_without_authenticated_user_identity(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_successful_invocation(
        _invocation_request(
            "test_echo", "test", "echo", actor=replace(DEFAULT_ACTOR, authenticated_user_id=None)
        )
    )

    record = _single_record(mcp_invocation_logging)

    assert record.attributes["mcp.tool.name"] == "test_echo"
    assert record.attributes["mcp.invocation.outcome"] == "success"
    assert "enduser.id" not in record.attributes or record.attributes["enduser.id"] == "unavailable"


def test_invocation_is_logged_without_agent_client_identity(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_successful_invocation(
        _invocation_request(
            "test_echo",
            "test",
            "echo",
            actor=replace(DEFAULT_ACTOR, agent_client_id=None, session_id=None),
        )
    )

    record = _single_record(mcp_invocation_logging)

    assert record.attributes["enduser.id"] == "user@example.com"
    assert (
        "mcp.client.id" not in record.attributes
        or record.attributes["mcp.client.id"] == "unavailable"
    )
    assert (
        "mcp.session.id" not in record.attributes
        or record.attributes["mcp.session.id"] == "unavailable"
    )


def test_tool_arguments_and_results_are_not_logged(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_successful_invocation(
        _invocation_request("crm_create_contact", "crm", "create_contact")
    )

    record_text = _record_text(_single_record(mcp_invocation_logging))

    assert "customer@example.com" not in record_text
    assert "cust_123" not in record_text
    assert "arguments" not in record_text
    assert "structured_content" not in record_text


def test_connector_tool_failure_is_logged_with_broad_failure_category(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_failed_invocation(
        _failed_invocation_request(
            invocation=_invocation_request("jira_create_ticket", "jira", "create_ticket"),
            failure_category=McpToolInvocationFailureCategory.CONNECTOR_ERROR,
        )
    )

    record = _single_record(mcp_invocation_logging)
    record_text = _record_text(record)

    assert record.attributes["mcp.tool.name"] == "jira_create_ticket"
    assert record.attributes["mcp.invocation.outcome"] == "failure"
    assert record.attributes["mcp.failure.category"] == "connector_error"
    assert "mcp.invocation.duration_ms" in record.attributes
    assert "Traceback" not in record_text


def test_unexpected_tool_failure_is_logged_without_sensitive_exception_details(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_failed_invocation(
        _failed_invocation_request(
            invocation=_invocation_request("test_echo", "test", "echo"),
            failure_category=McpToolInvocationFailureCategory.UNEXPECTED_ERROR,
        )
    )

    record_text = _record_text(_single_record(mcp_invocation_logging))

    assert "unexpected_error" in record_text
    assert "Traceback" not in record_text
    assert "RuntimeError" not in record_text


def test_authorization_denied_tool_invocation_is_logged(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    mcp_invocation_logging.complete_failed_invocation(
        _failed_invocation_request(
            invocation=_invocation_request("slack_post_message", "slack", "post_message"),
            failure_category=McpToolInvocationFailureCategory.AUTHORIZATION,
        )
    )

    record = _single_record(mcp_invocation_logging)

    assert record.attributes["mcp.tool.name"] == "slack_post_message"
    assert record.attributes["mcp.invocation.outcome"] == "failure"
    assert record.attributes["mcp.failure.category"] == "authorization"
    assert "arguments" not in _record_text(record)


def test_each_invocation_produces_one_log_record(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    for _ in range(3):
        mcp_invocation_logging.complete_successful_invocation(
            _invocation_request("test_echo", "test", "echo")
        )

    records = mcp_invocation_logging.invocation_logs()

    assert len(records) == 3
    assert all(record.attributes["mcp.invocation.outcome"] == "success" for record in records)
    assert all("mcp.invocation.duration_ms" in record.attributes for record in records)


def test_log_records_use_consistent_structured_shape(
    mcp_invocation_logging: McpToolInvocationLoggingDsl,
) -> None:
    invocation = _successful_invocation(
        _invocation_request("github_create_issue", "github", "create_issue")
    )

    record = mcp_invocation_logging.formatted_record_for(invocation)

    assert isinstance(record.body, str)
    assert isinstance(record.severity_text, str)
    assert record.attributes["mcp.interaction.type"] == "tool_invocation"
    assert record.attributes["mcp.tool.name"] == "github_create_issue"
    assert record.attributes["mcp.invocation.outcome"] == "success"
    assert "mcp.invocation.duration_ms" in record.attributes


def _invocation_request(
    tool_name: str,
    connector_id: str | None,
    operation_name: str | None,
    actor: McpInvocationActor | None = None,
) -> McpToolInvocationRequest:
    return McpToolInvocationRequest(
        tool=McpToolIdentity(
            tool_name=tool_name,
            connector_id=connector_id,
            operation_name=operation_name,
            connector_name=connector_id,
        ),
        actor=actor or DEFAULT_ACTOR,
        duration_ms=12.5,
    )


def _failed_invocation_request(
    *,
    invocation: McpToolInvocationRequest,
    failure_category: McpToolInvocationFailureCategory,
) -> McpFailedToolInvocationRequest:
    return McpFailedToolInvocationRequest(
        invocation=invocation,
        failure_category=failure_category,
    )


def _started_invocation(invocation: McpToolInvocationRequest) -> McpToolInvocationStarted:
    return McpToolInvocationStarted(
        interaction_type=McpInteractionType.TOOL_INVOCATION,
        tool=invocation.tool,
        actor=invocation.actor,
        started_at_unix_nano=1_700_000_000_000_000_000,
    )


def _successful_invocation(invocation: McpToolInvocationRequest) -> McpToolInvocationSucceeded:
    return McpToolInvocationSucceeded(
        started=_started_invocation(invocation), duration_ms=invocation.duration_ms
    )


def _failed_invocation(
    invocation: McpToolInvocationRequest,
    failure_category: McpToolInvocationFailureCategory,
) -> McpToolInvocationFailed:
    return McpToolInvocationFailed(
        started=_started_invocation(invocation),
        duration_ms=invocation.duration_ms,
        failure_category=failure_category,
    )


def _single_record(dsl: McpToolInvocationLoggingDsl) -> StructuredLogRecord:
    records = dsl.invocation_logs()
    assert len(records) == 1
    return records[0]


def _record_text(record: StructuredLogRecord) -> str:
    return f"{record.body} {record.severity_text} {dict(record.attributes)}"
