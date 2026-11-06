import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.tools import ToolResult
from fastmcp.exceptions import ToolError, ValidationError as ToolValidationError
from jsonschema.exceptions import SchemaError
from fastmcp.server.providers.proxy import ProxyTool

from umbod.logging import create_application_failure_signal
from umbod.core.invocation.failure_evidence import current_invocation_failure

from tests.umbod.mcp.connectors.downstream_mcp.personal_runtime_support import execution_case
from tests.umbod.core.connectors.downstream_mcp.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.connectors.downstream_mcp.test_personal_execution_pipeline import provider_for
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.logging import OpenTelemetryJsonFormatter, configure_logging
from umbod.mcp.connectors.downstream_mcp.tool_invocation import AuthorizedDownstreamProxyTool
from tests.umbod.mcp.connectors.downstream_mcp.signal_support import DiscardingAuditSink
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging import McpAuditRecorder
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import McpSignals, McpToolIdentity, SignalToolExecutionPipelineFactory
from umbod.mcp.logging.invocation.sink import create_default_mcp_tool_invocation_log_sink

__all__ = ["runtime_case"]

SENSITIVE = "sensitive-sentinel-token-url-arguments-results"


@pytest.fixture
def configured_signals(capsys: pytest.CaptureFixture[str]) -> Iterator[McpSignals]:
    application_failures = create_application_failure_signal()
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp")
    states = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate) for name in names}
    root.handlers = [handler for handler in root.handlers if not isinstance(handler.formatter, OpenTelemetryJsonFormatter)]
    try:
        yield create_mcp_signals(
            create_default_mcp_tool_invocation_log_sink(),
            InMemoryMcpMetricsRecorder(),
            McpAuditRecorder(DiscardingAuditSink(), "test", application_failures=application_failures),
         application_failures=application_failures)
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        for name, (handlers, propagate) in states.items():
            logging.getLogger(name).handlers = handlers
            logging.getLogger(name).propagate = propagate


def completion_records(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    output = capsys.readouterr()
    assert SENSITIVE not in output.out + output.err + caplog.text
    assert "https://" not in output.out + output.err
    assert "owner-token" not in output.out + output.err
    records = [json.loads(line) for line in output.out.splitlines()]
    return [record for record in records if record["body"] == "mcp tool invocation completed"]


def assert_failure(record: dict[str, Any], connector_id: str, name: str, tool: str, operation: str, mode: str, stage: str, reason: str) -> None:
    expected_categories = {
        "invalid_arguments": "validation",
        "admission_denied": "authorization",
        "authorization_rejected": "authorization",
        "downstream_tool_error": "tool_error",
    }
    category = expected_categories.get(reason, "connector_error")
    assert record["severity_text"] == ("ERROR" if category == "connector_error" else "WARNING")
    assert record["severity_number"] == (17 if category == "connector_error" else 13)
    assert record["resource"] == {"service.name": "failure-test"}
    assert record["trace_id"]
    attributes = record["attributes"]
    assert attributes["mcp.connector.id"] == connector_id
    assert attributes["mcp.connector.name"] == name
    assert attributes["mcp.tool.name"] == tool
    assert attributes["mcp.operation.name"] == operation
    assert attributes["mcp.failure.category"] == category
    assert attributes["mcp.failure.stage"] == stage
    assert attributes["mcp.failure.reason"] == reason
    assert attributes["mcp.execution_mode"] == mode
    if category != "connector_error":
        assert attributes["mcp.failure.origin"] == ("downstream_mcp" if reason == "downstream_tool_error" else "client_input")
        assert not any(key.startswith("exception.") for key in attributes)
    else:
        assert attributes["exception.type"]
        assert 'File "' in attributes["exception.stacktrace"]
        assert "[message omitted]" in attributes["exception.stacktrace"]
        assert "exception.message" not in attributes


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "internal", "result"])
async def test_shared_failures_enrich_normal_stdout_completion(configured_signals: McpSignals, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    configure_logging("failure-test", "INFO")
    async def invoke(self: object, arguments: dict[str, Any], **options: Any) -> ToolResult:
        if failure in {"exception", "internal"}:
            try:
                raise ValueError(SENSITIVE)
            except ValueError as error:
                if failure == "exception":
                    raise ToolError(SENSITIVE) from error
                raise RuntimeError(SENSITIVE) from error
        return ToolResult(content=SENSITIVE, structured_content={"secret": SENSITIVE}, meta={"secret": SENSITIVE}, is_error=True)

    class FailingProxyTool(ProxyTool):
        async def run(self, arguments: dict[str, Any], **options: Any) -> ToolResult:
            return await invoke(self, arguments, **options)

    def unused_client_factory() -> Client:
        raise AssertionError("Downstream client must not be created")

    async def ensure_access() -> None:
        return None

    held = AuthorizedDownstreamProxyTool(
        identity=McpToolIdentity(tool_name="Weather_forecast", connector_id="weather", connector_name="Weather", operation_name="forecast"),
        backend_tool=FailingProxyTool(
            client_factory=unused_client_factory,
            name="forecast",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        ),
        ensure_access=ensure_access,
        public_name="Weather_forecast",
        execution_pipeline=SignalToolExecutionPipelineFactory(configured_signals, PermitAllConnectorInvocationPolicy()).create(
            "Weather", lambda result: isinstance(result, ToolResult) and result.is_error,
        ),
    )
    monkeypatch.setattr("umbod.mcp.connectors.downstream_mcp.tool_invocation.get_context", lambda: object())
    result = await held.run({"city": SENSITIVE})
    assert result.is_error
    assert SENSITIVE not in repr(result)
    assert result.meta is None
    records = completion_records(capsys, caplog)
    assert len(records) == 1
    assert_failure(records[0], "weather", "Weather", "Weather_forecast", "forecast", "shared", "downstream", "downstream_tool_error" if failure == "result" else "downstream_exception")
    attributes = records[0]["attributes"]
    assert attributes["mcp.failure.origin"] == ("internal" if failure == "internal" else "downstream_mcp")
    if failure != "result":
        assert attributes["exception.type"] == ("RuntimeError" if failure == "internal" else "ToolError")
        assert "ValueError" in attributes["exception.stacktrace"]
        assert "in invoke" in attributes["exception.stacktrace"]
    assert current_invocation_failure() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,stage", [("context_unavailable", "context"), ("admission_denied", "admission"), ("invalid_arguments", "arguments"), ("contract_mismatch", "arguments"), ("invalid_output", "output"), ("authorization_rejected", "authorization"), ("authorization_health_unavailable", "authorization"), ("transport_failure", "transport"), ("runtime_failure", "runtime"), ("contract_mismatch", "transport"), ("target_expired", "transport"), ("timeout", "transport"), ("downstream_tool_error", "downstream")])
async def test_personal_failures_enrich_normal_stdout_completion(runtime_case: RuntimeCase, configured_signals: McpSignals, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, reason: str, stage: str) -> None:
    configure_logging("failure-test", "INFO")
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), configured_signals.invocation_completed.send)
    held = await provider.get_tool("Personal_read")
    arguments: dict[str, Any] = {"value": SENSITIVE}
    if reason == "context_unavailable":
        execution.contexts.contexts.clear()
    elif reason == "admission_denied":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif reason == "invalid_arguments":
        arguments = {"value": 12}
    elif reason == "contract_mismatch" and stage == "arguments":
        held.parameters = {"type": "invalid-schema-type"}
    elif reason == "invalid_output":
        execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [{"type": "text", "text": SENSITIVE}], "structuredContent": SENSITIVE})
    elif reason == "downstream_tool_error":
        execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [{"type": "text", "text": SENSITIVE}], "isError": True, "_meta": {"secret": SENSITIVE}})
    else:
        async def fail(command: PersonalToolCall) -> PersonalToolResult:
            if reason == "authorization_rejected":
                raise PersonalAuthorizationRejected(SENSITIVE)
            if reason == "authorization_health_unavailable":
                raise PersonalAuthorizationHealthUnavailable(SENSITIVE)
            if reason == "runtime_failure":
                raise RuntimeError(SENSITIVE)
            if reason == "transport_failure":
                raise PersonalRuntimeUnavailable(SENSITIVE)
            raise PersonalRuntimeUnavailable(SENSITIVE, diagnostic=InvocationFailureDiagnostic(execution_mode="personal", stage=stage, reason=reason))
        monkeypatch.setattr(execution.transport, "call_tool", fail)
    if reason == "invalid_arguments" or (reason == "contract_mismatch" and stage == "arguments"):
        failure_type = ToolValidationError if reason == "invalid_arguments" else RuntimeError
        with pytest.raises(failure_type, match="^Personal tool unavailable$"):
            await held.run(arguments)
    else:
        result = await held.run(arguments)
        assert SENSITIVE not in repr(result)
        assert result.meta is None
    records = completion_records(capsys, caplog)
    assert len(records) == 1
    assert_failure(records[0], "personal", "Personal", "Personal_read", "read", "personal", stage, reason)
    attributes = records[0]["attributes"]
    downstream = {"authorization_rejected", "transport_failure", "contract_mismatch", "target_expired", "timeout", "downstream_tool_error"}
    expected_origin = (
        "client_input" if reason in {"invalid_arguments", "admission_denied", "authorization_rejected"}
        else "downstream_mcp" if reason in downstream and stage != "arguments" else "internal"
    )
    assert attributes["mcp.failure.origin"] == expected_origin
    if reason == "runtime_failure":
        assert attributes["exception.type"] == "RuntimeError"
        assert "in fail" in attributes["exception.stacktrace"]
    if reason == "contract_mismatch" and stage == "arguments":
        assert attributes["exception.type"] == "PersonalToolPolicyInvalid"
    assert current_invocation_failure() is None


@pytest.mark.asyncio
async def test_personal_invalid_arguments_do_not_produce_framework_error_logs(
    runtime_case: RuntimeCase, configured_signals: McpSignals,
    caplog: pytest.LogCaptureFixture,
) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), configured_signals.invocation_completed.send)
    held = await provider.get_tool("Personal_read")
    server = FastMCP("test")
    server.add_tool(held)

    async with Client(server) as client:
        result = await client.call_tool("Personal_read", {"value": 12}, raise_on_error=False)

    assert result.is_error is True
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize(("schema", "severity", "category", "failure_type"), [
    ({"type": "object", "properties": {"value": {"type": "integer"}}}, "WARNING", "validation", ToolValidationError),
    ({"type": "invalid-schema-type"}, "ERROR", "connector_error", SchemaError),
])
async def test_shared_argument_rejections_warn_but_invalid_schemas_remain_errors(
    configured_signals: McpSignals, capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture, schema: dict[str, Any], severity: str, category: str,
    failure_type: type[Exception],
) -> None:
    configure_logging("failure-test", "INFO")

    def unused_client_factory() -> Client:
        raise AssertionError("Invalid arguments must not contact downstream")

    async def ensure_access() -> None:
        raise AssertionError("Invalid arguments must fail before execution")

    held = AuthorizedDownstreamProxyTool(
        identity=McpToolIdentity(tool_name="Shared_read", connector_id="shared", operation_name="read"),
        backend_tool=ProxyTool(client_factory=unused_client_factory, name="read", parameters=schema),
        ensure_access=ensure_access, public_name="Shared_read",
        execution_pipeline=SignalToolExecutionPipelineFactory(configured_signals, PermitAllConnectorInvocationPolicy()).create(
            "Shared", lambda result: isinstance(result, ToolResult) and result.is_error,
        ),
    )

    with pytest.raises(failure_type):
        await held.run({"value": SENSITIVE})

    records = completion_records(capsys, caplog)
    assert len(records) == 1
    assert records[0]["severity_text"] == severity
    assert records[0]["attributes"]["mcp.failure.category"] == category
    assert ("exception.stacktrace" in records[0]["attributes"]) == (severity == "ERROR")


@pytest.mark.asyncio
async def test_concurrent_failures_do_not_contaminate_success_or_later_invocations(runtime_case: RuntimeCase, configured_signals: McpSignals, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_logging("failure-test", "INFO")
    execution = await execution_case(runtime_case)
    held = await (await provider_for(execution, PermitAllConnectorInvocationPolicy(), configured_signals.invocation_completed.send)).get_tool("Personal_read")
    failed = asyncio.Event()
    success = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "unchanged"}})

    async def invoke(command: PersonalToolCall) -> PersonalToolResult:
        if command.arguments["value"] == "fail":
            failed.set()
            raise PersonalRuntimeUnavailable(SENSITIVE)
        await failed.wait()
        return success

    monkeypatch.setattr(execution.transport, "call_tool", invoke)
    failure, result = await asyncio.gather(held.run({"value": "fail"}), held.run({"value": "ok"}))
    assert failure.is_error
    assert not result.is_error
    assert result.structured_content == {"owner": "unchanged"}
    assert not (await held.run({"value": "again"})).is_error
    records = completion_records(capsys, caplog)
    assert len(records) == 3
    assert sum(record["severity_text"] == "ERROR" for record in records) == 1
    for record in records:
        if record["severity_text"] == "INFO":
            assert "mcp.failure.reason" not in record["attributes"]
            assert "mcp.failure.stage" not in record["attributes"]
            assert "mcp.execution_mode" not in record["attributes"]
            assert "mcp.failure.origin" not in record["attributes"]
            assert "exception.stacktrace" not in record["attributes"]
    assert current_invocation_failure() is None
