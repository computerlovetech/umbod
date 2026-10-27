import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastmcp.tools import ToolResult
from fastmcp.exceptions import ToolError

from umbod.core.invocation.failure_evidence import current_invocation_failure

from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import provider_for
from tests.umbod.mcp.downstream_mcp_connectors.test_provider import ProviderOptions, _downstream, _provider
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.logging import configure_logging
from umbod.mcp.connectors.downstream_mcp.tool_invocation import AuthorizedDownstreamProxyTool
from tests.umbod.mcp.downstream_mcp_connectors.signal_support import DiscardingAuditSink
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging import McpAuditRecorder
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import McpSignals
from umbod.mcp.logging.invocation.sink import create_default_mcp_tool_invocation_log_sink

__all__ = ["runtime_case"]

SENSITIVE = "sensitive-sentinel-token-url-arguments-results"


@pytest.fixture
def configured_signals(capsys: pytest.CaptureFixture[str]) -> Iterator[McpSignals]:
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp")
    states = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate) for name in names}
    root.handlers = [handler for handler in root.handlers if not getattr(handler, "_umbod_otel_stdout_handler", False)]
    try:
        yield create_mcp_signals(
            create_default_mcp_tool_invocation_log_sink(),
            InMemoryMcpMetricsRecorder(),
            McpAuditRecorder(DiscardingAuditSink(), "test"),
        )
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        for name, (handlers, propagate) in states.items():
            logging.getLogger(name).handlers = handlers
            logging.getLogger(name).propagate = propagate


def completion_records(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    output = capsys.readouterr()
    assert SENSITIVE not in output.out + output.err + caplog.text
    records = [json.loads(line) for line in output.out.splitlines()]
    return [record for record in records if record["body"] == "mcp tool invocation completed"]


def assert_failure(record: dict[str, Any], connector_id: str, name: str, tool: str, operation: str, mode: str, stage: str, reason: str) -> None:
    assert record["severity_text"] == "ERROR"
    assert record["severity_number"] == 17
    assert record["resource"] == {"service.name": "failure-test"}
    assert record["trace_id"]
    attributes = record["attributes"]
    assert attributes["mcp.connector.id"] == connector_id
    assert attributes["mcp.connector.name"] == name
    assert attributes["mcp.tool.name"] == tool
    assert attributes["mcp.operation.name"] == operation
    assert attributes["mcp.failure.category"] == "connector_error"
    assert attributes["mcp.failure.stage"] == stage
    assert attributes["mcp.failure.reason"] == reason
    assert attributes["mcp.execution_mode"] == mode
    if reason == "downstream_tool_error":
        assert attributes["mcp.failure.origin"] == "downstream_mcp"
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
    provider, *_ = await _provider({"weather": _downstream()}, ProviderOptions({"weather": "Weather"}, configured_signals))
    held = await provider.get_tool("Weather_forecast")
    assert isinstance(held, AuthorizedDownstreamProxyTool)

    async def invoke(self: object, arguments: dict[str, Any], **options: Any) -> ToolResult:
        if failure in {"exception", "internal"}:
            try:
                raise ValueError(SENSITIVE)
            except ValueError as error:
                if failure == "exception":
                    raise ToolError(SENSITIVE) from error
                raise RuntimeError(SENSITIVE) from error
        return ToolResult(content=SENSITIVE, structured_content={"secret": SENSITIVE}, meta={"secret": SENSITIVE}, is_error=True)

    monkeypatch.setattr(type(held._backend_tool), "run", invoke)
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
@pytest.mark.parametrize("reason,stage", [("context_unavailable", "context"), ("admission_denied", "admission"), ("invalid_arguments", "arguments"), ("invalid_output", "output"), ("authorization_rejected", "authorization"), ("authorization_health_unavailable", "authorization"), ("transport_failure", "transport"), ("runtime_failure", "runtime"), ("contract_mismatch", "transport"), ("target_expired", "transport"), ("timeout", "transport"), ("downstream_tool_error", "downstream")])
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
    if reason == "invalid_arguments":
        with pytest.raises(RuntimeError, match="^Personal tool unavailable$"):
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
    assert attributes["mcp.failure.origin"] == ("downstream_mcp" if reason in downstream else "internal")
    if reason == "runtime_failure":
        assert attributes["exception.type"] == "RuntimeError"
        assert "in fail" in attributes["exception.stacktrace"]
    assert current_invocation_failure() is None


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
