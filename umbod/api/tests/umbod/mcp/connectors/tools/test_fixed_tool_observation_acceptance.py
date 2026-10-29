from tests.support.native_tool_states import enabled_native_tool_states
import hashlib
import json
from io import StringIO
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from tests.support.connector_plugins import SlackAdminConfiguration
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolMapping,
    InMemoryConnectorPublishingStore,
)
from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.native.tools import register_connector_tools
from umbod.mcp.logging import (
    McpAuditIdentityAdapter,
    McpAuditRecorder,
    StdoutMcpAuditEventSink,
    StructuredMcpAuditFormatter,
)
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals import McpToolInvocationCompleted, SignalToolExecutionPipelineFactory
from umbod.mcp.middleware import McpAuditMiddleware
from pydantic import SecretStr


async def _observed_server(mode: str) -> tuple[FastMCP, InMemoryMcpMetricsRecorder, InMemoryMcpToolInvocationLogSink, StringIO]:
    configurations = InMemoryConnectorCurrentConfigurationStore()
    await configurations.save_current_configuration(
        "slack",
        SlackAdminConfiguration(workspace_name="Computerlove", bot_token=SecretStr("token"), default_channel_id="channel"),
    )
    publications = InMemoryConnectorPublishingStore()
    await publications.publish_connector("slack")
    metrics = InMemoryMcpMetricsRecorder()
    logs = InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())
    stream = StringIO()
    audit = McpAuditRecorder(StdoutMcpAuditEventSink(StructuredMcpAuditFormatter(), stream), "test")
    server = FastMCP("test", middleware=[McpAuditMiddleware(audit, McpAuditIdentityAdapter(), mode)])
    signals = create_mcp_signals(logs, metrics, audit)
    server.invocation_signals = signals

    def operation(limit: int) -> dict[str, int]:
        if limit < 0:
            raise ValueError("Connector operation rejected limit")
        return {"limit": limit}

    await register_connector_tools(
        server,
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()),
        connector_registrations=[{"id": "slack", "display_name": "Slack", "capability_description": "Slack operations", "configuration_schema": SlackAdminConfiguration}],
        connector_configuration_store=configurations,
        connector_publishing_store=publications,
        connector_tool_runtime_state_store=enabled_native_tool_states(("slack", "first"), ("slack", "second")),
        connector_tool_mappings=[
            ConnectorToolMapping("slack", "first", "First operation", operation),
            ConnectorToolMapping("slack", "second", "Second operation", operation),
        ],
        connector_tool_exposure_mode=mode,
        connector_code_execution_timeout_seconds=0.01,
    )
    return server, metrics, logs, stream


def _audit_records(stream: StringIO) -> list[dict[str, Any]]:
    return [
        record["attributes"]
        for line in stream.getvalue().splitlines()
        if (record := json.loads(line))["attributes"]["mcp.audit.activity_type"] == "tool_invocation"
    ]


def _counts(metrics: InMemoryMcpMetricsRecorder, metric_name: str) -> dict[tuple[str, str], float]:
    return {
        (sample.labels["tool_name"], sample.labels["outcome"]): sample.value
        for sample in metrics.metric_samples()
        if sample.name == metric_name and sample.value
    }


@pytest.mark.asyncio
async def test_custom_receivers_are_isolated_and_extend_real_tool_execution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    server, metrics, logs, stream = await _observed_server("gateway")
    other_server, _, _, _ = await _observed_server("gateway")
    received: list[McpToolInvocationCompleted] = []
    other_received: list[McpToolInvocationCompleted] = []

    def failing_action(event: McpToolInvocationCompleted) -> None:
        raise RuntimeError("private-receiver-detail")

    server.invocation_signals.invocation_completed.connect("test.failing_action", failing_action)
    server.invocation_signals.invocation_completed.connect("test.notification", received.append)
    other_server.invocation_signals.invocation_completed.connect("test.notification", other_received.append)
    async with Client(server) as client:
        result = await client.call_tool("execute_tool", {"tool_name": "slack_first", "arguments": {"limit": 1}})

    assert result.is_error is False
    assert {event.started.tool.tool_name for event in received} == {"execute_tool", "slack_first"}
    assert len(received) == 2
    assert other_received == []
    assert _counts(metrics, "umbod_mcp_tool_requests_total") == {("execute_tool", "success"): 1}
    assert _counts(metrics, "umbod_mcp_tool_invocations_total") == {("slack_first", "success"): 1}
    assert len(logs.invocation_records()) == 2
    assert len(_audit_records(stream)) == 2
    assert "test.failing_action" in caplog.text
    assert "private-receiver-detail" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,tool_name,arguments,connector_names", [
    ("gateway", "execute_tool", {"tool_name": "slack_first", "arguments": {"limit": 1}}, {"slack_first"}),
    ("codemode", "execute_code", {"code": "slack_first(limit=1)\nslack_second(limit=2)"}, {"slack_first", "slack_second"}),
])
async def test_fixed_execution_records_one_request_and_distinct_connector_completions(
    mode: str, tool_name: str, arguments: dict[str, Any], connector_names: set[str],
) -> None:
    server, metrics, logs, stream = await _observed_server(mode)
    async with Client(server) as client:
        result = await client.call_tool(tool_name, arguments)

    assert result.is_error is False
    assert _counts(metrics, "umbod_mcp_tool_requests_total") == {(tool_name, "success"): 1}
    assert _counts(metrics, "umbod_mcp_tool_invocations_total") == {(name, "success"): 1 for name in connector_names}
    records = logs.invocation_records()
    request_records = [record.attributes for record in records if record.attributes["mcp.invocation.scope"] == "request"]
    connector_records = [record.attributes for record in records if record.attributes["mcp.invocation.scope"] == "connector"]
    assert len(request_records) == 1
    assert request_records[0]["mcp.tool.name"] == tool_name
    assert {record["mcp.tool.name"] for record in connector_records} == connector_names
    audit_records = _audit_records(stream)
    assert len(audit_records) == 1 + len(connector_names)
    request_audit = [record for record in audit_records if record["mcp.tool.name"] == tool_name]
    assert len(request_audit) == 1
    if mode == "codemode":
        assert request_audit[0]["mcp.code.hash"] == hashlib.sha256(arguments["code"].encode()).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,tool_name,arguments,request_outcome", [
    ("gateway", "execute_tool", {"tool_name": "slack_first", "arguments": {"limit": -1}}, "failure"),
    ("codemode", "execute_code", {"code": "slack_first(limit=-1)"}, "failure"),
])
async def test_connector_failure_is_counted_once_independently_of_outer_request(
    mode: str, tool_name: str, arguments: dict[str, Any], request_outcome: str,
) -> None:
    server, metrics, logs, stream = await _observed_server(mode)
    async with Client(server) as client:
        await client.call_tool(tool_name, arguments, raise_on_error=False)

    assert _counts(metrics, "umbod_mcp_tool_requests_total") == {(tool_name, request_outcome): 1}
    assert _counts(metrics, "umbod_mcp_tool_invocations_total") == {("slack_first", "failure"): 1}
    records = logs.invocation_records()
    assert len(records) == 2
    assert {
        (record.attributes["mcp.invocation.scope"], record.attributes["mcp.invocation.outcome"])
        for record in records
    } == {("request", request_outcome), ("connector", "failure")}
    assert len(_audit_records(stream)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("code,outcome", [("if :", "failure"), ("while True:\n    pass", "timeout")])
async def test_codemode_failure_before_nested_call_records_only_request_failure(code: str, outcome: str) -> None:
    server, metrics, logs, stream = await _observed_server("codemode")
    async with Client(server) as client:
        result = await client.call_tool("execute_code", {"code": code})

    assert result.is_error is False
    assert result.structured_content["outcome"] == outcome
    assert result.structured_content["nested_calls"] == []
    assert _counts(metrics, "umbod_mcp_tool_requests_total") == {("execute_code", "failure"): 1}
    assert _counts(metrics, "umbod_mcp_tool_invocations_total") == {}
    assert len(logs.invocation_records()) == 1
    assert logs.invocation_records()[0].attributes["mcp.invocation.scope"] == "request"
    records = _audit_records(stream)
    assert len(records) == 1
    assert records[0]["mcp.audit.outcome"] == "failure"
    assert records[0]["mcp.code.hash"] == hashlib.sha256(code.encode()).hexdigest()


@pytest.mark.asyncio
async def test_unknown_gateway_tool_records_request_failure_without_connector_completion() -> None:
    server, metrics, logs, stream = await _observed_server("gateway")
    async with Client(server) as client:
        result = await client.call_tool("execute_tool", {"tool_name": "missing", "arguments": {}}, raise_on_error=False)

    assert result.is_error is True
    assert _counts(metrics, "umbod_mcp_tool_requests_total") == {("execute_tool", "failure"): 1}
    assert _counts(metrics, "umbod_mcp_tool_invocations_total") == {}
    assert len(logs.invocation_records()) == 1
    assert logs.invocation_records()[0].attributes["mcp.invocation.scope"] == "request"
    records = _audit_records(stream)
    assert len(records) == 1
    assert records[0]["mcp.audit.outcome"] == "failure"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,execute_name,version", [("gateway", "execute_tool", "1.0.0"), ("codemode", "execute_code", "2.0.0")])
async def test_fixed_search_is_observed_and_registration_preserves_metadata(mode: str, execute_name: str, version: str) -> None:
    server, metrics, logs, stream = await _observed_server(mode)
    tools = {name: await server.get_tool(name) for name in (execute_name, "search_tools")}
    assert tools[execute_name].tags == {"connectors", mode}
    assert tools[execute_name].meta == {"version": version}
    assert tools["search_tools"].tags == {"connectors", "gateway"}
    assert tools["search_tools"].meta == {"version": "1.0.0"}
    async with Client(server) as client:
        result = await client.call_tool("search_tools", {"query": "first"})

    assert result.is_error is False
    assert _counts(metrics, "umbod_mcp_tool_requests_total") == {("search_tools", "success"): 1}
    assert _counts(metrics, "umbod_mcp_tool_invocations_total") == {}
    assert len(logs.invocation_records()) == 1
    assert logs.invocation_records()[0].attributes["mcp.invocation.scope"] == "request"
    assert len(_audit_records(stream)) == 1
