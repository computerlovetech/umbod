from collections.abc import Iterator

import pytest
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families
from starlette.testclient import TestClient

from umbod.mcp.metrics import (
    CompletedToolInvocation,
    InMemoryMcpMetricsRecorder,
    InvocationOutcome,
    McpMetricsRecorder,
    PrometheusMcpMetricsRecorder,
)
from umbod.mcp.metrics.http_server import create_metrics_app


@pytest.fixture
def invocations() -> tuple[CompletedToolInvocation, ...]:
    return tuple(
        CompletedToolInvocation(
            connector_name=connector,
            tool_name=tool,
            outcome=outcome,
            duration_seconds=0.25,
        )
        for connector, tool, outcome in (
            ("github", "create_issue", InvocationOutcome.SUCCESS),
            ("github", "create_issue", InvocationOutcome.SUCCESS),
            ("github", "create_issue", InvocationOutcome.FAILURE),
            ("github", "search", InvocationOutcome.SUCCESS),
            ("jira", "create_issue", InvocationOutcome.SUCCESS),
        )
    )


@pytest.fixture
def expected_counts() -> dict[tuple[str, str, str], int]:
    return {
        ("github", "create_issue", "success"): 2,
        ("github", "create_issue", "failure"): 1,
        ("github", "search", "success"): 1,
        ("jira", "create_issue", "success"): 1,
    }


def _record_invocations(
    recorder: McpMetricsRecorder, invocations: tuple[CompletedToolInvocation, ...]
) -> None:
    for invocation in invocations:
        recorder.record_completed_invocation(invocation)


@pytest.fixture
def metrics_client(
    invocations: tuple[CompletedToolInvocation, ...],
) -> Iterator[TestClient]:
    recorder = PrometheusMcpMetricsRecorder()
    _record_invocations(recorder, invocations)
    with TestClient(create_metrics_app(recorder)) as client:
        yield client


def test_completed_invocations_are_scraped_with_approved_dimensions(
    metrics_client: TestClient, expected_counts: dict[tuple[str, str, str], int]
) -> None:
    response = metrics_client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    samples = tuple(
        sample
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    )
    for metric_name, multiplier in (
        ("umbod_mcp_tool_invocations_total", 1),
        ("umbod_mcp_tool_invocation_duration_seconds_count", 1),
        ("umbod_mcp_tool_invocation_duration_seconds_sum", 0.25),
    ):
        matching = tuple(sample for sample in samples if sample.name == metric_name)
        assert {
            (sample.labels["connector_name"], sample.labels["tool_name"], sample.labels["outcome"]): sample.value
            for sample in matching
        } == {labels: count * multiplier for labels, count in expected_counts.items()}
        assert all(
            set(sample.labels) == {"connector_name", "tool_name", "outcome"}
            for sample in matching
        )


def test_inmemory_recorder_aggregates_the_same_approved_dimensions(
    invocations: tuple[CompletedToolInvocation, ...],
    expected_counts: dict[tuple[str, str, str], int],
) -> None:
    recorder = InMemoryMcpMetricsRecorder()
    _record_invocations(recorder, invocations)
    samples = recorder.metric_samples()
    for metric_name in (
        "umbod_mcp_tool_invocations_total",
        "umbod_mcp_tool_invocation_duration_seconds_count",
    ):
        assert {
            (sample.labels["connector_name"], sample.labels["tool_name"], sample.labels["outcome"]): sample.value
            for sample in samples
            if sample.name == metric_name
        } == expected_counts
    assert all(
        set(sample.labels) == {"connector_name", "tool_name", "outcome"} for sample in samples
    )


def test_inmemory_recorder_reset_clears_only_its_own_samples(
    invocations: tuple[CompletedToolInvocation, ...],
) -> None:
    first = InMemoryMcpMetricsRecorder()
    second = InMemoryMcpMetricsRecorder()
    _record_invocations(first, invocations)
    assert second.metric_samples() == ()
    _record_invocations(second, invocations)
    original_samples = second.metric_samples()
    assert original_samples

    first.reset()

    assert first.metric_samples() == ()
    assert second.metric_samples() == original_samples
