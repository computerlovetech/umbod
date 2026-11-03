import ssl
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import anyio
import httpcore2
import pytest

from tests.umbod.core.connectors.downstream_mcp.adapters.personal_runtime.conftest import ScriptedNetwork, ScriptedResolver
from tests.umbod.core.connectors.downstream_mcp.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.connectors.downstream_mcp.test_personal_tools_s3_contracts import approved_tool
from tests.umbod.mcp.connectors.downstream_mcp.personal_runtime_support import execution_case
from tests.umbod.mcp.connectors.downstream_mcp.test_failure_logging import SENSITIVE, assert_failure, completion_records, configured_signals
from tests.umbod.mcp.connectors.downstream_mcp.test_personal_execution_pipeline import provider_for
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import FastMCPPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.http import PersonalHttpTransport
from umbod.core.connectors.downstream_mcp.models import DiscoveredTool
from mcp import types
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.logging import configure_logging
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalToolRuntime
from umbod.mcp.signals import McpSignals

__all__ = ["runtime_case", "configured_signals"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,reason,status",
    [
        ("401", "authorization_rejected", 401),
        ("403", "http_rejected", 403),
        ("429", "http_rejected", 429),
        ("503", "http_rejected", 503),
        ("encoding", "content_encoding_rejected", 200),
        ("charset", "charset_rejected", 200),
        ("length", "invalid_content_length", 200),
        ("interim", "http_rejected", 503),
        ("header_size", "response_size_exceeded", 200),
        ("stream_size", "response_size_exceeded", 200),
        ("aggregate_header", "aggregate_size_exceeded", 200),
        ("aggregate_stream", "aggregate_size_exceeded", 200),
        ("request_size", "request_size_exceeded", 0),
        ("protocol", "protocol_rejected", 200),
        ("timeout", "timeout", 0),
        ("expired", "target_expired", 0),
        ("network", "network_failure", 0),
        ("unexpected", "runtime_failure", 0),
        ("cleanup", "http_rejected", 503),
        ("inventory_snapshot", "runtime_failure", 200),
        ("inventory_cleanup_timeout", "runtime_failure", 200),
        ("cleanup_timeout", "timeout", 0),
    ],
)
async def test_scripted_network_failures_reach_public_tool_and_serialized_stdout(
    runtime_case: RuntimeCase,
    configured_signals: McpSignals,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    reason: str,
    status: int,
) -> None:
    configure_logging("failure-test", "INFO")
    execution = await execution_case(runtime_case)
    network = ScriptedNetwork()
    network.tools = [{"name": "read", "inputSchema": approved_tool("read").input_schema}]
    cleanup_cancellations: list[bool] = []
    limits = PersonalRuntimeLimits(operation_timeout_seconds=1, maximum_response_bytes=2048, maximum_total_bytes=8192, maximum_request_bytes=2048, maximum_tool_pages=3)
    def clock() -> datetime:
        return runtime_case.query.now + (timedelta(days=1) if scenario == "expired" else timedelta())
    if scenario.isdecimal():
        network.status = int(scenario)
        network.response_headers["www-authenticate"] = SENSITIVE
    elif scenario == "interim":
        network.interim_response = True
        network.status = 503
        network.read_size = 3
    elif scenario == "encoding":
        network.response_headers["content-encoding"] = "gzip"
    elif scenario == "length":
        network.response_headers["content-length"] = "invalid-" + SENSITIVE
    elif scenario == "charset":
        network.response_headers["content-type"] = "application/json; charset=utf-7"
    elif scenario in {"header_size", "stream_size", "aggregate_header", "aggregate_stream"}:
        network.call_result = {"content": [{"type": "text", "text": SENSITIVE * 100}]}
        network.chunked_call = scenario.endswith("stream") or scenario == "stream_size"
        if scenario.startswith("aggregate"):
            limits = limits.model_copy(update={"maximum_response_bytes": 16384, "maximum_total_bytes": 2048})
    elif scenario == "protocol":
        network.raw_body = ("{\"jsonrpc\":\"" + SENSITIVE).encode()
    elif scenario == "timeout":
        network.delay = 2
        limits = limits.model_copy(update={"operation_timeout_seconds": 0.05})
    elif scenario in {"network", "unexpected"}:
        async def fail_connect(*arguments: object, **options: object) -> httpcore2.AsyncNetworkStream:
            if scenario == "network":
                raise httpcore2.ConnectError(SENSITIVE)
            raise RuntimeError(SENSITIVE)
        monkeypatch.setattr(network, "connect_tcp", fail_connect)
    elif scenario == "cleanup":
        network.status = 503
        async def fail_close(self: object) -> None:
            raise RuntimeError(SENSITIVE)
        monkeypatch.setattr("umbod.core.connectors.downstream_mcp.adapters.personal_runtime.http.PersonalHttpTransport.aclose", fail_close)
    if scenario in {"inventory_snapshot", "inventory_cleanup_timeout", "cleanup_timeout"}:
        network.session = True
        network.cleanup_status = 204
    if scenario in {"inventory_snapshot", "inventory_cleanup_timeout"}:
        def fail_inventory_mapping(tool: types.Tool) -> DiscoveredTool:
            raise RuntimeError(SENSITIVE)
        monkeypatch.setattr("umbod.core.connectors.downstream_mcp.adapters.personal_runtime.transport.map_sdk_tool", fail_inventory_mapping)
    if scenario in {"inventory_cleanup_timeout", "cleanup_timeout"}:
        original_close = PersonalHttpTransport.aclose
        async def stall_cleanup(bridge: PersonalHttpTransport) -> None:
            await original_close(bridge)
            try:
                await anyio.sleep_forever()
            finally:
                cleanup_cancellations.append(True)
        monkeypatch.setattr(PersonalHttpTransport, "aclose", stall_cleanup)
    transport = FastMCPPersonalMcpTransport(limits, clock, ScriptedResolver(), lambda: network, ssl.create_default_context())
    runtime = McpPersonalToolRuntime(execution.contexts, runtime_case.bundle.personal_tool_access, transport, lambda: runtime_case.query.now)
    execution = replace(execution, runtime=runtime)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), configured_signals.invocation_completed.send)
    held = await provider.get_tool("Personal_read")
    arguments: dict[str, Any] = {"value": SENSITIVE * (100 if scenario == "request_size" else 1)}
    started_at = anyio.current_time()
    with anyio.fail_after(3):
        result = await held.run(arguments)
    assert anyio.current_time() - started_at < 2
    assert result.is_error
    assert SENSITIVE not in repr(result)
    records = completion_records(capsys, caplog)
    assert len(records) == 1
    internal_failure = scenario in {"unexpected", "inventory_snapshot", "inventory_cleanup_timeout", "cleanup_timeout"}
    stage = "authorization" if scenario == "401" else "runtime" if internal_failure else "transport"
    attributes = records[0]["attributes"]
    assert attributes["mcp.failure.reason"] == reason
    assert attributes["mcp.downstream.response_received"] is bool(status)
    if status:
        assert attributes["mcp.downstream.http.status_code"] == status
    else:
        assert "mcp.downstream.http.status_code" not in attributes
    assert attributes["mcp.failure.origin"] == ("internal" if internal_failure else "downstream_mcp")
    if scenario in {"inventory_snapshot", "inventory_cleanup_timeout"}:
        assert attributes["exception.type"] == "RuntimeError"
        assert "in fail_inventory_mapping" in attributes["exception.stacktrace"]
        assert "stall_cleanup" not in attributes["exception.stacktrace"]
        assert any(method == "DELETE" for method, _, _ in network.requests)
    if scenario in {"inventory_cleanup_timeout", "cleanup_timeout"}:
        assert cleanup_cancellations
    if scenario == "cleanup_timeout":
        assert attributes["exception.type"] == "TimeoutError"
        assert any(message.get("method") == "tools/call" for _, _, message in network.requests)
    if scenario in {"unexpected", "network"}:
        assert "in fail_connect" in attributes["exception.stacktrace"]
        assert attributes["exception.type"] == ("RuntimeError" if scenario == "unexpected" else "ConnectError")
    if scenario == "cleanup":
        assert "fail_close" not in attributes["exception.stacktrace"]
    assert len(network.connections) <= (6 if network.session else 4)
    assert sum(method == "GET" for method, _, _ in network.requests) <= 1
    assert sum(message.get("method") == "tools/call" for _, _, message in network.requests) <= 1
    assert_failure(records[0], "personal", "Personal", "Personal_read", "read", "personal", stage, reason)
