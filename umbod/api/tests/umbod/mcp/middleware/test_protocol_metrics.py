import asyncio
from collections.abc import Sequence

import mcp.types as mt
import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.middleware.middleware import MiddlewareContext
from fastmcp.tools import FunctionTool
from fastmcp.tools.base import Tool
from prometheus_client.parser import text_string_to_metric_families

from umbod.mcp.metrics.protocol_models import (
    CompletedProtocolRequest,
    ProtocolMethod,
    ProtocolOutcome,
    SuccessfulToolsList,
)
from umbod.mcp.metrics.protocol_recorder import McpProtocolMetricsRecorder
from umbod.mcp.metrics.prometheus import PrometheusMcpMetricsRecorder
from umbod.mcp.middleware.protocol_metrics import McpProtocolMetricsMiddleware


class RecordingMetrics:
    def __init__(self, failing: bool = False) -> None:
        self.requests: list[CompletedProtocolRequest] = []
        self.lists: list[SuccessfulToolsList] = []
        self.failing = failing

    def record_protocol_request(self, observation: CompletedProtocolRequest) -> None:
        self.requests.append(observation)
        if self.failing:
            raise RuntimeError("metrics unavailable")

    def record_tools_list(self, observation: SuccessfulToolsList) -> None:
        self.lists.append(observation)
        if self.failing:
            raise RuntimeError("metrics unavailable")


class ManualClock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def named_tool() -> str:
    return "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_count", [0, 2])
@pytest.mark.parametrize("method", tuple(ProtocolMethod))
@pytest.mark.parametrize("outcome", tuple(ProtocolOutcome))
@pytest.mark.parametrize("failing", [False, True])
async def test_protocol_metrics_preserve_full_request_outcome(
    method: ProtocolMethod, outcome: ProtocolOutcome, failing: bool, tool_count: int
) -> None:
    recorder = RecordingMetrics(failing)
    port: McpProtocolMetricsRecorder = recorder
    clock = ManualClock()
    middleware = McpProtocolMetricsMiddleware(port, clock=clock)
    failure = RuntimeError("request failed")
    cancellation = asyncio.CancelledError()
    tools: Sequence[Tool] = tuple(
        FunctionTool.from_function(named_tool) for _ in range(tool_count)
    )

    async def finish() -> None:
        assert recorder.requests == []
        clock.now += 0.25
        await asyncio.sleep(0)
        clock.now += 0.5
        if outcome == ProtocolOutcome.ERROR:
            raise failure
        if outcome == ProtocolOutcome.CANCELLED:
            raise cancellation

    async def initialize(
        context: MiddlewareContext[mt.InitializeRequest],
    ) -> None:
        await finish()

    async def list_tools(
        context: MiddlewareContext[mt.ListToolsRequest],
    ) -> Sequence[Tool]:
        await finish()
        return tools

    async def invoke() -> object:
        if method == ProtocolMethod.INITIALIZE:
            return await middleware.on_initialize(
                MiddlewareContext(message=mt.InitializeRequest(params=mt.InitializeRequestParams(
                    protocolVersion="2025-06-18", capabilities=mt.ClientCapabilities(),
                    clientInfo=mt.Implementation(name="private-client", version="1"),
                )), method=method.value), initialize,
            )
        return await middleware.on_list_tools(
            MiddlewareContext(message=mt.ListToolsRequest(), method=method.value), list_tools,
        )

    if outcome == ProtocolOutcome.SUCCESS:
        result = await invoke()
        assert result is (None if method == ProtocolMethod.INITIALIZE else tools)
    else:
        expected = failure if outcome == ProtocolOutcome.ERROR else cancellation
        with pytest.raises(type(expected)) as raised:
            await invoke()
        assert raised.value is expected

    assert recorder.requests == [CompletedProtocolRequest(
        method=method, outcome=outcome, duration_seconds=0.75,
    )]
    assert recorder.lists == (
        [SuccessfulToolsList(tool_count=tool_count)]
        if method == ProtocolMethod.LIST_TOOLS and outcome == ProtocolOutcome.SUCCESS else []
    )


def test_prometheus_protocol_metrics_have_only_bounded_dimensions() -> None:
    adapter = PrometheusMcpMetricsRecorder()
    port: McpProtocolMetricsRecorder = adapter
    for method in ProtocolMethod:
        for outcome in ProtocolOutcome:
            port.record_protocol_request(CompletedProtocolRequest(
                method=method, outcome=outcome, duration_seconds=0.75,
            ))
    port.record_tools_list(SuccessfulToolsList(tool_count=0))
    port.record_tools_list(SuccessfulToolsList(tool_count=3))
    samples = [sample for family in text_string_to_metric_families(
        adapter.prometheus_text().decode()
    ) for sample in family.samples]
    durations = [sample for sample in samples
                 if sample.name == "umbod_mcp_protocol_request_duration_seconds_sum"]
    assert len(durations) == 6
    assert {(sample.labels["method"], sample.labels["outcome"]) for sample in durations} == {
        (method.value, outcome.value) for method in ProtocolMethod for outcome in ProtocolOutcome
    }
    assert all(sample.value == 0.75 and set(sample.labels) == {"method", "outcome"}
               for sample in durations)
    counts = [sample for sample in samples
              if sample.name == "umbod_mcp_protocol_request_duration_seconds_count"]
    assert len(counts) == 6
    assert all(sample.value == 1 for sample in counts)
    lists = {sample.name: sample for sample in samples
             if sample.name.startswith("umbod_mcp_tools_list_tool_count_")}
    assert lists["umbod_mcp_tools_list_tool_count_sum"].value == 3
    assert lists["umbod_mcp_tools_list_tool_count_count"].value == 2
    assert all(not sample.labels for name, sample in lists.items()
               if not name.endswith("_bucket"))


@pytest.mark.asyncio
async def test_real_mcp_client_records_initialize_and_listing_without_tool_identity_labels() -> None:
    recorder = RecordingMetrics()
    port: McpProtocolMetricsRecorder = recorder
    server = FastMCP("protocol-observations", middleware=[McpProtocolMetricsMiddleware(port, clock=ManualClock())])
    server.add_tool(FunctionTool.from_function(named_tool))
    async with Client(server, mode="legacy") as client:
        assert [tool.name for tool in await client.list_tools()] == ["named_tool"]
    assert {request.method for request in recorder.requests} == set(ProtocolMethod)
    assert all(request.outcome == ProtocolOutcome.SUCCESS for request in recorder.requests)
    assert recorder.lists == [SuccessfulToolsList(tool_count=1)]


def test_prometheus_protocol_metrics_are_registry_local() -> None:
    first = PrometheusMcpMetricsRecorder()
    second = PrometheusMcpMetricsRecorder()
    port: McpProtocolMetricsRecorder = first
    port.record_protocol_request(CompletedProtocolRequest(
        method=ProtocolMethod.INITIALIZE, outcome=ProtocolOutcome.SUCCESS, duration_seconds=0,
    ))
    assert b'umbod_mcp_protocol_request_duration_seconds_count{method="initialize",outcome="success"} 1.0' in first.prometheus_text()
    assert b'umbod_mcp_protocol_request_duration_seconds_count{' not in second.prometheus_text()
