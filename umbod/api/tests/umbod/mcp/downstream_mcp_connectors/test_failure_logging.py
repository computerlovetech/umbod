import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastmcp.tools import ToolResult

from tests.umbod.core.downstream_mcp_connectors.personal_tools.runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import provider_for
from tests.umbod.mcp.downstream_mcp_connectors.test_provider import ProviderOptions, _downstream, _provider
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import PersonalAuthorizationHealthUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolResult
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.logging import configure_logging
from umbod.mcp.connectors.downstream_mcp.tool_invocation import AuthorizedDownstreamProxyTool
from umbod.mcp.logging import ConnectorToolInvocationLogger
from umbod.mcp.logging.invocation.recorder import InvocationLogSinkToolInvocationLogger
from umbod.mcp.logging.invocation.sink import create_default_mcp_tool_invocation_log_sink

__all__ = ["runtime_case"]

SENSITIVE = "sensitive-sentinel-token-url-arguments-results"


@pytest.fixture
def configured_logger(capsys: pytest.CaptureFixture[str]) -> Iterator[ConnectorToolInvocationLogger]:
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp")
    states = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate) for name in names}
    root.handlers = [handler for handler in root.handlers if not getattr(handler, "_umbod_otel_stdout_handler", False)]
    try:
        yield InvocationLogSinkToolInvocationLogger(create_default_mcp_tool_invocation_log_sink())
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
    assert not any(key.startswith("exception.") for key in attributes)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "result"])
async def test_shared_failures_enrich_normal_stdout_completion(configured_logger: ConnectorToolInvocationLogger, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    configure_logging("failure-test", "INFO")
    provider, *_ = await _provider({"weather": _downstream()}, ProviderOptions({"weather": "Weather"}, configured_logger))
    held = await provider.get_tool("Weather_forecast")
    assert isinstance(held, AuthorizedDownstreamProxyTool)

    async def invoke(self: object, arguments: dict[str, Any], **options: Any) -> ToolResult:
        if failure == "exception":
            raise RuntimeError(SENSITIVE)
        return ToolResult(content=SENSITIVE, structured_content={"secret": SENSITIVE}, meta={"secret": SENSITIVE}, is_error=True)

    monkeypatch.setattr(type(held._backend_tool), "run", invoke)
    monkeypatch.setattr("umbod.mcp.connectors.downstream_mcp.tool_invocation.get_context", lambda: object())
    result = await held.run({"city": SENSITIVE})
    assert result.is_error
    assert SENSITIVE not in repr(result)
    assert result.meta is None
    records = completion_records(capsys, caplog)
    assert len(records) == 1
    assert_failure(records[0], "weather", "Weather", "Weather_forecast", "forecast", "shared", "downstream", "downstream_exception" if failure == "exception" else "downstream_tool_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,stage", [("context_unavailable", "context"), ("admission_denied", "admission"), ("invalid_arguments", "arguments"), ("invalid_output", "output"), ("authorization_rejected", "authorization"), ("authorization_health_unavailable", "authorization"), ("transport_failure", "transport"), ("runtime_failure", "runtime"), ("contract_mismatch", "transport"), ("target_expired", "transport"), ("timeout", "transport"), ("downstream_tool_error", "downstream")])
async def test_personal_failures_enrich_normal_stdout_completion(runtime_case: RuntimeCase, configured_logger: ConnectorToolInvocationLogger, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, reason: str, stage: str) -> None:
    configure_logging("failure-test", "INFO")
    execution = await execution_case(runtime_case)
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), configured_logger)
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
        execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [{"type": "text", "text": SENSITIVE}], "isError": True})
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


@pytest.mark.asyncio
async def test_concurrent_failures_do_not_contaminate_success_or_later_invocations(runtime_case: RuntimeCase, configured_logger: ConnectorToolInvocationLogger, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_logging("failure-test", "INFO")
    execution = await execution_case(runtime_case)
    held = await provider_for(execution, PermitAllConnectorInvocationPolicy(), configured_logger).get_tool("Personal_read")
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
