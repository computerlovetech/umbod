import json
from dataclasses import replace
from io import StringIO

import pytest
from pydantic import SecretStr

from umbod.core.invocation.failure_evidence import (
    InvocationExceptionEvidence,
    InvocationFailureOrigin,
    InvocationReturnedFailure,
    exception_evidence,
)
from umbod.mcp.signals.events import (
    McpInteractionType,
    McpInvocationActor,
    McpInvocationCorrelation,
    McpToolIdentity,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
    McpToolInvocationStarted,
)
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import McpToolInvocationLogSink, StdoutMcpToolInvocationLogSink


@pytest.fixture
def failed_invocation() -> McpToolInvocationFailed:
    return McpToolInvocationFailed(
        started=McpToolInvocationStarted(
            interaction_type=McpInteractionType.TOOL_INVOCATION,
            tool=McpToolIdentity("example_tool", "example", "operation"),
            actor=McpInvocationActor(),
            started_at_unix_nano=1,
            correlation=McpInvocationCorrelation("trace", "span"),
        ),
        duration_ms=1.0,
        failure_category=McpToolInvocationFailureCategory.CONNECTOR_ERROR,
    )


def _exception_with_sensitive_chain() -> BaseException:
    credential = SecretStr("unwrapped-credential-sentinel")
    try:
        try:
            raise ValueError(credential.get_secret_value())
        except ValueError as error:
            raise RuntimeError("downstream-body-sentinel") from error
    except RuntimeError as error:
        return error


def _export(event: McpToolInvocationFailed) -> dict[str, object]:
    output = StringIO()
    sink: McpToolInvocationLogSink = StdoutMcpToolInvocationLogSink(
        StructuredMcpToolInvocationLogFormatter(), output
    )
    sink.record_invocation_completed(event)
    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


@pytest.mark.parametrize("origin", list(InvocationFailureOrigin))
def test_completion_exports_safe_exception_chain_and_origin(
    failed_invocation: McpToolInvocationFailed, origin: InvocationFailureOrigin
) -> None:
    evidence = exception_evidence(_exception_with_sensitive_chain(), origin)

    record = _export(replace(failed_invocation, evidence=evidence))

    attributes = record["attributes"]
    assert attributes["mcp.failure.origin"] == origin.value
    assert attributes["exception.type"] == "RuntimeError"
    stacktrace = attributes["exception.stacktrace"]
    assert "ValueError" in stacktrace
    assert "RuntimeError" in stacktrace
    assert "_exception_with_sensitive_chain" in stacktrace
    assert "direct cause" in stacktrace
    assert "unwrapped-credential-sentinel" not in json.dumps(record)
    assert "downstream-body-sentinel" not in json.dumps(record)
    assert "get_secret_value" not in stacktrace
    assert "credential =" not in stacktrace
    assert record["trace_id"] == "trace"
    assert record["span_id"] == "span"


def test_returned_error_has_origin_without_invented_traceback(
    failed_invocation: McpToolInvocationFailed,
) -> None:
    record = _export(replace(
        failed_invocation,
        evidence=InvocationReturnedFailure(InvocationFailureOrigin.MCP),
    ))

    assert record["attributes"]["mcp.failure.origin"] == "downstream_mcp"
    assert "exception.stacktrace" not in record["attributes"]
    assert "exception.type" not in record["attributes"]


def test_exception_group_exports_safe_nested_types(
    failed_invocation: McpToolInvocationFailed,
) -> None:
    error = ExceptionGroup("group-secret-sentinel", [
        _exception_with_sensitive_chain(), OSError("transport-secret-sentinel"),
    ])
    record = _export(replace(
        failed_invocation,
        evidence=exception_evidence(error, InvocationFailureOrigin.INTERNAL),
    ))

    stacktrace = record["attributes"]["exception.stacktrace"]
    assert "ExceptionGroup" in stacktrace
    assert "OSError" in stacktrace
    assert "ValueError" in stacktrace
    assert "sentinel" not in json.dumps(record)


def test_exception_snapshot_does_not_retain_live_exception() -> None:
    evidence = exception_evidence(_exception_with_sensitive_chain(), InvocationFailureOrigin.INTERNAL)

    assert isinstance(evidence, InvocationExceptionEvidence)
    assert set(vars(evidence)) == {"origin", "exception_type", "stacktrace"}
    assert isinstance(evidence.stacktrace, str)
