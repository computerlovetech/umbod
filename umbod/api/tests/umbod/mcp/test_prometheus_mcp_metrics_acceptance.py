from collections.abc import Callable, Iterator

import pytest
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families
from starlette.testclient import TestClient

from umbod.mcp.metrics import (
    CompletedToolInvocation,
    InMemoryMcpMetricsRecorder,
    InvocationOutcome,
    InvocationScope,
    McpMetricsRecorder,
    PrometheusMcpMetricsRecorder,
    ToolInvocationMetricIdentity,
)
from umbod.mcp.metrics.http_server import create_metrics_app
from umbod.mcp.metrics.in_memory import McpMetricSample


@pytest.fixture
def invocations() -> tuple[CompletedToolInvocation, ...]:
    return tuple(
        CompletedToolInvocation(
            scope=InvocationScope.CONNECTOR,
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
        ("github", "search", "failure"): 0,
        ("jira", "create_issue", "success"): 1,
        ("jira", "create_issue", "failure"): 0,
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


@pytest.fixture(params=["inmemory", "prometheus"])
def recorder_samples(
    request: pytest.FixtureRequest,
) -> tuple[McpMetricsRecorder, Callable[[], tuple[McpMetricSample, ...]]]:
    if request.param == "inmemory":
        recorder = InMemoryMcpMetricsRecorder()
        return recorder, recorder.metric_samples
    prometheus = PrometheusMcpMetricsRecorder()

    def samples() -> tuple[McpMetricSample, ...]:
        return tuple(
            McpMetricSample(name=sample.name, labels=sample.labels, value=sample.value)
            for family in text_string_to_metric_families(prometheus.prometheus_text().decode())
            for sample in family.samples
            if sample.name.startswith("umbod_mcp_tool_")
        )

    return prometheus, samples


@pytest.mark.parametrize("scope", tuple(InvocationScope))
def test_initialization_exposes_both_zero_outcomes_without_observations(
    recorder_samples: tuple[McpMetricsRecorder, Callable[[], tuple[McpMetricSample, ...]]],
    scope: InvocationScope,
) -> None:
    recorder, samples = recorder_samples
    identity = ToolInvocationMetricIdentity(scope=scope, connector_name="github", tool_name="search")
    recorder.initialize_invocation(identity)
    recorder.initialize_invocation(identity)
    observed = tuple(sample for sample in samples() if not sample.name.endswith("_created"))
    assert observed
    assert {sample.labels["outcome"] for sample in observed} == {"success", "failure"}
    assert all(sample.value == 0 for sample in observed)
    duration_count_name = (
        "umbod_mcp_tool_invocation_duration_seconds_count" if scope == InvocationScope.CONNECTOR
        else "umbod_mcp_tool_request_duration_seconds_count"
    )
    assert {sample.labels["outcome"] for sample in observed if sample.name == duration_count_name} == {
        "success", "failure"
    }
    assert {sample.name for sample in observed if sample.name.endswith("_total")} == {
        "umbod_mcp_tool_invocations_total" if scope == InvocationScope.CONNECTOR
        else "umbod_mcp_tool_requests_total"
    }
    assert all(
        ("connector_name" in sample.labels) == (scope == InvocationScope.CONNECTOR)
        for sample in observed
    )


@pytest.mark.parametrize("scope", tuple(InvocationScope))
def test_initialization_preserves_existing_counts(
    recorder_samples: tuple[McpMetricsRecorder, Callable[[], tuple[McpMetricSample, ...]]],
    scope: InvocationScope,
) -> None:
    recorder, samples = recorder_samples
    invocation = CompletedToolInvocation(
        scope=scope, connector_name="github", tool_name="search",
        outcome=InvocationOutcome.SUCCESS, duration_seconds=0.25,
    )
    recorder.record_completed_invocation(invocation)
    before = samples()
    identity = ToolInvocationMetricIdentity(scope=scope, connector_name="github", tool_name="search")
    recorder.initialize_invocation(identity)
    recorder.initialize_invocation(identity)
    assert samples() == before
    counts = tuple(sample for sample in before if sample.name.endswith(("_total", "_count")))
    assert all(sample.value == (1 if sample.labels["outcome"] == "success" else 0) for sample in counts)


def test_request_and_connector_scopes_are_isolated_and_request_connectors_are_not_labels(
    recorder_samples: tuple[McpMetricsRecorder, Callable[[], tuple[McpMetricSample, ...]]],
) -> None:
    recorder, samples = recorder_samples
    for scope, connector in (
        (InvocationScope.CONNECTOR, "github"),
        (InvocationScope.REQUEST, "github"),
        (InvocationScope.REQUEST, "jira"),
    ):
        recorder.record_completed_invocation(CompletedToolInvocation(
            scope=scope, connector_name=connector, tool_name="search",
            outcome=InvocationOutcome.SUCCESS, duration_seconds=0.25,
        ))
    counts = {sample.name: sample for sample in samples()
              if sample.name.endswith("_total") and sample.labels["outcome"] == "success"}
    assert counts["umbod_mcp_tool_invocations_total"].value == 1
    assert counts["umbod_mcp_tool_requests_total"].value == 2
    assert counts["umbod_mcp_tool_requests_total"].labels == {"tool_name": "search", "outcome": "success"}


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
