from typing import Dict, Iterable, Tuple

from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample

from umbod.mcp.metrics import (
    CompletedToolInvocation,
    InvocationOutcome,
    McpMetricsRecorder,
    PrometheusMcpMetricsRecorder,
)


def _record_invocation(recorder: McpMetricsRecorder) -> None:
    recorder.record_completed_invocation(
        CompletedToolInvocation(
            connector_name="github",
            tool_name="create_issue",
            outcome=InvocationOutcome.SUCCESS,
            duration_seconds=0.25,
        )
    )


def _samples(text: bytes) -> Dict[str, Tuple[Sample, ...]]:
    families: Iterable[object] = text_string_to_metric_families(text.decode("utf-8"))
    return {family.name: tuple(family.samples) for family in families}


def test_prometheus_recorder_records_count_and_duration_through_protocol() -> None:
    recorder = PrometheusMcpMetricsRecorder()

    _record_invocation(recorder)
    samples = _samples(recorder.prometheus_text())

    expected_labels = {
        "connector_name": "github",
        "tool_name": "create_issue",
        "outcome": "success",
    }
    invocation_count = next(
        sample
        for sample in samples["umbod_mcp_tool_invocations"]
        if sample.name == "umbod_mcp_tool_invocations_total"
    )
    duration_count = next(
        sample
        for sample in samples["umbod_mcp_tool_invocation_duration_seconds"]
        if sample.name == "umbod_mcp_tool_invocation_duration_seconds_count"
    )
    duration_sum = next(
        sample
        for sample in samples["umbod_mcp_tool_invocation_duration_seconds"]
        if sample.name == "umbod_mcp_tool_invocation_duration_seconds_sum"
    )
    assert invocation_count.labels == expected_labels
    assert invocation_count.value == 1
    assert duration_count.labels == expected_labels
    assert duration_count.value == 1
    assert duration_sum.labels == expected_labels
    assert duration_sum.value == 0.25


def test_prometheus_recorder_exposes_standard_platform_and_gc_metrics() -> None:
    recorder = PrometheusMcpMetricsRecorder()

    samples = _samples(recorder.prometheus_text())

    sample_names = {sample.name for family_samples in samples.values() for sample in family_samples}
    assert "python_info" in sample_names
    assert any(name.startswith("python_gc_") for name in sample_names)
