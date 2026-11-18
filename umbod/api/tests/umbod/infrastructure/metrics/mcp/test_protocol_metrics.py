from prometheus_client.parser import text_string_to_metric_families

from umbod.infrastructure.metrics.mcp import PrometheusMcpMetricsRecorder
from umbod.mcp.metrics import (
    CompletedProtocolRequest,
    McpProtocolMetricsRecorder,
    ProtocolMethod,
    ProtocolOutcome,
    SuccessfulToolsList,
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


def test_prometheus_protocol_metrics_are_registry_local() -> None:
    first = PrometheusMcpMetricsRecorder()
    second = PrometheusMcpMetricsRecorder()
    port: McpProtocolMetricsRecorder = first
    port.record_protocol_request(CompletedProtocolRequest(
        method=ProtocolMethod.INITIALIZE, outcome=ProtocolOutcome.SUCCESS, duration_seconds=0,
    ))
    assert b'umbod_mcp_protocol_request_duration_seconds_count{method="initialize",outcome="success"} 1.0' in first.prometheus_text()
    assert b'umbod_mcp_protocol_request_duration_seconds_count{' not in second.prometheus_text()
