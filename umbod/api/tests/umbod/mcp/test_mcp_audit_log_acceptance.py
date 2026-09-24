import json

from dataclasses import dataclass
from io import StringIO
from typing import Any, Callable, Mapping, Protocol

import pytest

from umbod.mcp.logging.audit import (
    McpAuditActivityType,
    McpAnonymousAuditActor,
    McpAuthenticatedAuditActor,
    McpAuditClientMetadata,
    McpAuditCorrelation,
    McpAuditDenied,
    McpAuditEvent,
    McpAuditFailure,
    McpAuditFailureCategory,
    McpAuditOutcome,
    McpAuditResult,
    McpAuditSuccess,
    McpToolAuditTarget,
    StdoutMcpAuditEventSink,
    StructuredMcpAuditFormatter,
)


@dataclass(frozen=True)
class AuthenticatedClientConnection:
    user_id: str
    client_id: str
    client_name: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class ToolDiscoveryRequest:
    user_id: str
    client_id: str
    session_id: str | None = None


@dataclass(frozen=True)
class ToolInvocationRequest:
    user_id: str
    client_id: str
    tool_name: str
    allowed: bool = True
    succeeds: bool = True
    session_id: str | None = None


@dataclass(frozen=True)
class UnauthenticatedActivityAttempt:
    activity_type: McpAuditActivityType
    client_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class AuthenticatedAuditActivity:
    activity_type: McpAuditActivityType
    user_id: str
    client_id: str
    client_name: str | None
    session_id: str | None
    tool_name: str | None
    outcome: McpAuditOutcome
    failure_category: McpAuditFailureCategory | None


@dataclass(frozen=True)
class ToolInvocationActivity:
    user_id: str
    client_id: str
    tool_name: str
    allowed: bool
    succeeds: bool
    session_id: str | None


class McpAuditOutputDriver(Protocol):
    def stdout_audit_output(self) -> str: ...

    def stdout_observability_output(self) -> str: ...


class CapturedMcpAuditOutputDriver:
    def __init__(self) -> None:
        self._audit_stream = StringIO()
        self._observability_stream = StringIO()
        self._audit_sink = StdoutMcpAuditEventSink(
            StructuredMcpAuditFormatter(), self._audit_stream
        )
        self._trace_id = "trace-123"

    def __getattr__(self, name: str) -> Callable[..., None]:
        if name == "connect_authenticated_client":
            return lambda user_id, client_id, client_name=None, session_id=None: (
                _record_authenticated_activity(
                    self,
                    AuthenticatedAuditActivity(
                        McpAuditActivityType.CLIENT_CONNECTION,
                        user_id,
                        client_id,
                        client_name,
                        session_id,
                        None,
                        McpAuditOutcome.SUCCESS,
                        None,
                    ),
                )
            )
        if name == "discover_tools":
            return lambda user_id, client_id, session_id=None: _record_authenticated_activity(
                self,
                AuthenticatedAuditActivity(
                    McpAuditActivityType.TOOL_DISCOVERY,
                    user_id,
                    client_id,
                    None,
                    session_id,
                    None,
                    McpAuditOutcome.SUCCESS,
                    None,
                ),
            )
        if name == "invoke_tool":
            return lambda user_id, client_id, tool_name, **kwargs: _record_tool_invocation(
                self,
                ToolInvocationActivity(
                    user_id,
                    client_id,
                    tool_name,
                    bool(kwargs.get("allowed", True)),
                    bool(kwargs.get("succeeds", True)),
                    kwargs.get("session_id"),
                ),
            )
        if name == "attempt_unauthenticated_activity":
            return lambda activity_type, client_id=None, tool_name=None: (
                _record_unauthenticated_activity(self, activity_type, client_id, tool_name)
            )
        raise AttributeError(name)

    def stdout_audit_output(self) -> str:
        return self._audit_stream.getvalue()

    def stdout_observability_output(self) -> str:
        return self._observability_stream.getvalue()


def _record_tool_invocation(
    driver: CapturedMcpAuditOutputDriver, activity: ToolInvocationActivity
) -> None:
    outcome, failure_category = _tool_invocation_result(activity.allowed, activity.succeeds)
    _record_authenticated_activity(
        driver,
        AuthenticatedAuditActivity(
            McpAuditActivityType.TOOL_INVOCATION,
            activity.user_id,
            activity.client_id,
            None,
            activity.session_id,
            activity.tool_name,
            outcome,
            failure_category,
        ),
    )
    if outcome == McpAuditOutcome.SUCCESS:
        driver._observability_stream.write(
            json.dumps(
                {"body": "mcp tool invocation completed", "trace_id": driver._trace_id},
                sort_keys=True,
            )
            + "\n"
        )


def _tool_invocation_result(
    allowed: bool, succeeds: bool
) -> tuple[McpAuditOutcome, McpAuditFailureCategory | None]:
    if not allowed:
        return McpAuditOutcome.DENIED, McpAuditFailureCategory.AUTHORIZATION
    if not succeeds:
        return McpAuditOutcome.FAILURE, McpAuditFailureCategory.CONNECTOR_ERROR
    return McpAuditOutcome.SUCCESS, None


def _record_unauthenticated_activity(
    driver: CapturedMcpAuditOutputDriver,
    activity_type: McpAuditActivityType,
    client_id: str | None,
    tool_name: str | None,
) -> None:
    event = McpAuditEvent(
        activity_type=activity_type,
        actor=McpAnonymousAuditActor(),
        client=McpAuditClientMetadata({"client_id": client_id}),
        target=McpToolAuditTarget(server_name="umbod", tool_name=tool_name, attributes={}),
        result=McpAuditDenied(McpAuditFailureCategory.AUTHENTICATION),
        occurred_at_unix_nano=1,
        correlation=McpAuditCorrelation(trace_id=driver._trace_id, span_id=None),
    )
    driver._audit_sink.record_mcp_activity(event)


def _record_authenticated_activity(
    driver: CapturedMcpAuditOutputDriver, activity: AuthenticatedAuditActivity
) -> None:
    event = McpAuditEvent(
        activity_type=activity.activity_type,
        actor=McpAuthenticatedAuditActor(activity.user_id),
        client=McpAuditClientMetadata(
            {
                key: value
                for key, value in {
                    "client_id": activity.client_id,
                    "client_name": activity.client_name,
                    "session_id": activity.session_id,
                }.items()
                if value is not None
            }
        ),
        target=McpToolAuditTarget(
            server_name="umbod", tool_name=activity.tool_name, attributes={}
        ),
        result=_activity_result(activity),
        occurred_at_unix_nano=1,
        correlation=McpAuditCorrelation(trace_id=driver._trace_id, span_id=None),
    )
    driver._audit_sink.record_mcp_activity(event)


def _activity_result(activity: AuthenticatedAuditActivity) -> McpAuditResult:
    if activity.outcome == McpAuditOutcome.SUCCESS:
        return McpAuditSuccess()
    if activity.failure_category is None:
        raise ValueError("failure category is required")
    if activity.outcome == McpAuditOutcome.DENIED:
        return McpAuditDenied(activity.failure_category)
    return McpAuditFailure(activity.failure_category)


@pytest.fixture
def mcp_audit() -> McpAuditOutputDriver:
    return CapturedMcpAuditOutputDriver()


def test_authenticated_mcp_client_connection_is_audited(mcp_audit: McpAuditOutputDriver) -> None:
    request = AuthenticatedClientConnection(
        "user@example.com", "claude-code", "Claude Code", "session-123"
    )
    _driver_method(mcp_audit, "connect_authenticated_client")(
        request.user_id,
        request.client_id,
        request.client_name,
        request.session_id,
    )

    record = _single_audit_record(mcp_audit)

    assert record["body"] == "mcp audit event"
    assert record["severity_text"] == "INFO"
    assert record["attributes"]["mcp.audit.activity_type"] == "client_connection"
    assert record["attributes"]["enduser.id"] == "user@example.com"
    assert record["attributes"]["mcp.client.id"] == "claude-code"
    assert record["attributes"]["mcp.client.name"] == "Claude Code"
    assert record["attributes"]["mcp.session.id"] == "session-123"
    assert record["attributes"]["mcp.audit.outcome"] == "success"
    assert "trace_id" in record
    assert _does_not_contain_sensitive_payload(record)


def test_authenticated_tool_discovery_is_audited(mcp_audit: McpAuditOutputDriver) -> None:
    request = ToolDiscoveryRequest("user@example.com", "cursor", "session-456")
    _driver_method(mcp_audit, "discover_tools")(
        request.user_id, request.client_id, request.session_id
    )

    record = _single_audit_record(mcp_audit)

    assert record["attributes"]["mcp.audit.activity_type"] == "tool_discovery"
    assert record["attributes"]["enduser.id"] == "user@example.com"
    assert record["attributes"]["mcp.client.id"] == "cursor"
    assert record["attributes"]["mcp.audit.outcome"] == "success"
    assert _does_not_contain_sensitive_payload(record)


def test_successful_authenticated_tool_invocation_is_audited_and_correlated(
    mcp_audit: McpAuditOutputDriver,
) -> None:
    request = ToolInvocationRequest(
        "user@example.com", "claude-code", "github_create_issue", allowed=True, succeeds=True
    )
    _driver_method(mcp_audit, "invoke_tool")(
        request.user_id,
        request.client_id,
        request.tool_name,
        allowed=request.allowed,
        succeeds=request.succeeds,
        session_id=request.session_id,
    )

    audit_record = _single_audit_record(mcp_audit)
    observability_record = _single_observability_record(mcp_audit)

    assert audit_record["attributes"]["mcp.audit.activity_type"] == "tool_invocation"
    assert audit_record["attributes"]["mcp.tool.name"] == "github_create_issue"
    assert audit_record["attributes"]["mcp.audit.outcome"] == "success"
    assert audit_record["trace_id"] == observability_record["trace_id"]
    assert audit_record["body"] != observability_record["body"]


def test_failed_authenticated_tool_invocation_is_audited_without_payload(
    mcp_audit: McpAuditOutputDriver,
) -> None:
    request = ToolInvocationRequest(
        "user@example.com", "claude-code", "jira_create_ticket", allowed=True, succeeds=False
    )
    _driver_method(mcp_audit, "invoke_tool")(
        request.user_id,
        request.client_id,
        request.tool_name,
        allowed=request.allowed,
        succeeds=request.succeeds,
        session_id=request.session_id,
    )

    record = _single_audit_record(mcp_audit)

    assert record["attributes"]["mcp.tool.name"] == "jira_create_ticket"
    assert record["attributes"]["mcp.audit.outcome"] == "failure"
    assert record["attributes"]["mcp.failure.category"] == "connector_error"
    assert record["severity_text"] == "ERROR"
    assert _does_not_contain_sensitive_payload(record)


def test_authorization_denied_authenticated_tool_attempt_is_audited(
    mcp_audit: McpAuditOutputDriver,
) -> None:
    request = ToolInvocationRequest(
        "user@example.com", "claude-code", "slack_post_message", allowed=False
    )
    _driver_method(mcp_audit, "invoke_tool")(
        request.user_id,
        request.client_id,
        request.tool_name,
        allowed=request.allowed,
        succeeds=request.succeeds,
        session_id=request.session_id,
    )

    record = _single_audit_record(mcp_audit)

    assert record["attributes"]["enduser.id"] == "user@example.com"
    assert record["attributes"]["mcp.client.id"] == "claude-code"
    assert record["attributes"]["mcp.tool.name"] == "slack_post_message"
    assert record["attributes"]["mcp.audit.outcome"] == "denied"
    assert record["attributes"]["mcp.failure.category"] == "authorization"


def test_denied_unauthenticated_mcp_attempt_is_audited(mcp_audit: McpAuditOutputDriver) -> None:
    request = UnauthenticatedActivityAttempt(McpAuditActivityType.TOOL_DISCOVERY, "unknown-client")
    _driver_method(mcp_audit, "attempt_unauthenticated_activity")(
        request.activity_type,
        request.client_id,
        request.tool_name,
    )

    record = _single_audit_record(mcp_audit)

    assert record["attributes"]["mcp.audit.activity_type"] == "tool_discovery"
    assert record["attributes"]["mcp.actor.anonymous"] is True
    assert record["attributes"]["mcp.client.id"] == "unknown-client"
    assert record["attributes"]["mcp.audit.outcome"] == "denied"
    assert record["attributes"]["mcp.failure.category"] == "authentication"
    assert "enduser.id" not in record["attributes"]
    assert _does_not_contain_sensitive_payload(record)


def test_audit_event_uses_available_identity_metadata_only(mcp_audit: McpAuditOutputDriver) -> None:
    request = ToolDiscoveryRequest("user@example.com", "claude-code")
    _driver_method(mcp_audit, "discover_tools")(
        request.user_id, request.client_id, request.session_id
    )

    record = _single_audit_record(mcp_audit)

    assert record["attributes"]["enduser.id"] == "user@example.com"
    assert record["attributes"]["mcp.client.id"] == "claude-code"
    assert (
        "mcp.session.id" not in record["attributes"]
        or record["attributes"]["mcp.session.id"] == "unavailable"
    )


def test_audit_records_are_stdout_only_and_open_telemetry_structured(
    mcp_audit: McpAuditOutputDriver,
) -> None:
    request = AuthenticatedClientConnection("user@example.com", "claude-code")
    _driver_method(mcp_audit, "connect_authenticated_client")(
        request.user_id,
        request.client_id,
        request.client_name,
        request.session_id,
    )

    output = mcp_audit.stdout_audit_output()
    record = _single_json_line(output)

    assert set(record).issuperset({"body", "severity_text", "attributes", "trace_id"})
    assert record["attributes"]["mcp.audit.stream"] == "mcp_audit"
    assert "query" not in dir(mcp_audit)
    assert "audit_records" not in dir(mcp_audit)


def _driver_method(driver: McpAuditOutputDriver, name: str) -> Callable[..., None]:
    method = getattr(driver, name)
    assert callable(method)
    return method


def _single_audit_record(driver: McpAuditOutputDriver) -> dict[str, Any]:
    return _single_json_line(driver.stdout_audit_output())


def _single_observability_record(driver: McpAuditOutputDriver) -> dict[str, Any]:
    return _single_json_line(driver.stdout_observability_output())


def _single_json_line(output: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert isinstance(decoded, dict)
    return decoded


def _does_not_contain_sensitive_payload(record: Mapping[str, Any]) -> bool:
    text = json.dumps(record, sort_keys=True)
    sensitive_fragments = [
        "arguments",
        "structured_content",
        "token",
        "secret",
        "password",
        "customer@example.com",
        "Traceback",
    ]
    return all(fragment not in text for fragment in sensitive_fragments)
