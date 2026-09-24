from enum import StrEnum
from typing import Mapping, Protocol, Sequence

import pytest
from pydantic import BaseModel, ConfigDict, PositiveFloat, PositiveInt

from umbod.mcp.metrics import (
    CompletedToolInvocation as RecorderCompletedToolInvocation,
)
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.metrics import InvocationOutcome as RecorderInvocationOutcome


INVOCATION_COUNT_METRIC = "umbod_mcp_tool_invocations_total"
INVOCATION_DURATION_COUNT_METRIC = "umbod_mcp_tool_invocation_duration_seconds_count"


class InvocationOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class MetricsAccess(StrEnum):
    PRIVATE_NETWORK = "private_network"
    PUBLIC_INGRESS = "public_ingress"


class CompletedToolInvocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    connector_name: str
    tool_name: str
    outcome: InvocationOutcome
    duration_seconds: PositiveFloat


class ToolInvocationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: InvocationOutcome


class MetricSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    labels: Mapping[str, str]
    value: float


class MetricsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    accessible: bool
    prometheus_compatible: bool
    samples: Sequence[MetricSample]


class ServiceEndpoints(BaseModel):
    model_config = ConfigDict(frozen=True)

    mcp_port: PositiveInt
    metrics_port: PositiveInt
    metrics_path: str


class McpMetricsAcceptanceBoundary(Protocol):
    async def complete_invocation(
        self,
        invocation: CompletedToolInvocation,
    ) -> ToolInvocationResult: ...

    async def read_metrics(self, access: MetricsAccess) -> MetricsResponse: ...

    async def service_endpoints(self) -> ServiceEndpoints: ...

    async def restart_mcp_process(self) -> None: ...


class InMemoryMcpMetricsProtocolDriver:
    def __init__(self, recorder: InMemoryMcpMetricsRecorder) -> None:
        self._recorder = recorder

    async def complete_invocation(
        self,
        invocation: CompletedToolInvocation,
    ) -> ToolInvocationResult:
        self._recorder.record_completed_invocation(
            RecorderCompletedToolInvocation(
                connector_name=invocation.connector_name,
                tool_name=invocation.tool_name,
                outcome=RecorderInvocationOutcome(invocation.outcome.value),
                duration_seconds=invocation.duration_seconds,
            )
        )
        return ToolInvocationResult(outcome=invocation.outcome)

    async def read_metrics(self, access: MetricsAccess) -> MetricsResponse:
        if access is MetricsAccess.PUBLIC_INGRESS:
            return MetricsResponse(
                accessible=False,
                prometheus_compatible=False,
                samples=(),
            )
        invocation_samples = tuple(
            MetricSample(name=sample.name, labels=sample.labels, value=sample.value)
            for sample in self._recorder.metric_samples()
        )
        base_samples = (
            MetricSample(name=INVOCATION_COUNT_METRIC, labels={}, value=0),
            MetricSample(name=INVOCATION_DURATION_COUNT_METRIC, labels={}, value=0),
            MetricSample(name="process_start_time_seconds", labels={}, value=0),
            MetricSample(name="python_info", labels={}, value=1),
        )
        return MetricsResponse(
            accessible=True,
            prometheus_compatible=True,
            samples=base_samples + invocation_samples,
        )

    async def service_endpoints(self) -> ServiceEndpoints:
        return ServiceEndpoints(mcp_port=8000, metrics_port=8001, metrics_path="/metrics")

    async def restart_mcp_process(self) -> None:
        self._recorder.reset()


class McpMetricsDsl:
    def __init__(self, boundary: McpMetricsAcceptanceBoundary) -> None:
        self._boundary = boundary

    async def complete_invocation(
        self,
        connector_name: str,
        tool_name: str,
        outcome: InvocationOutcome,
        duration_seconds: float = 0.25,
    ) -> ToolInvocationResult:
        return await self._boundary.complete_invocation(
            CompletedToolInvocation(
                connector_name=connector_name,
                tool_name=tool_name,
                outcome=outcome,
                duration_seconds=duration_seconds,
            )
        )

    async def private_metrics(self) -> MetricsResponse:
        return await self._boundary.read_metrics(MetricsAccess.PRIVATE_NETWORK)

    async def public_metrics(self) -> MetricsResponse:
        return await self._boundary.read_metrics(MetricsAccess.PUBLIC_INGRESS)

    async def service_endpoints(self) -> ServiceEndpoints:
        return await self._boundary.service_endpoints()

    async def restart_mcp_process(self) -> None:
        await self._boundary.restart_mcp_process()


@pytest.fixture
def mcp_metrics() -> McpMetricsDsl:
    boundary = InMemoryMcpMetricsProtocolDriver(InMemoryMcpMetricsRecorder())
    return McpMetricsDsl(boundary)


@pytest.mark.asyncio
async def test_successful_invocation_is_reflected_in_metrics(
    mcp_metrics: McpMetricsDsl,
) -> None:
    await mcp_metrics.complete_invocation("github", "create_issue", InvocationOutcome.SUCCESS)

    metrics = await mcp_metrics.private_metrics()

    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "github", "create_issue", "success") == 1
    assert (
        _sample_value(
            metrics, INVOCATION_DURATION_COUNT_METRIC, "github", "create_issue", "success"
        )
        == 1
    )


@pytest.mark.asyncio
async def test_failed_invocation_is_reflected_in_metrics(mcp_metrics: McpMetricsDsl) -> None:
    await mcp_metrics.complete_invocation("jira", "create_ticket", InvocationOutcome.FAILURE)

    metrics = await mcp_metrics.private_metrics()

    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "jira", "create_ticket", "failure") == 1
    assert (
        _sample_value(metrics, INVOCATION_DURATION_COUNT_METRIC, "jira", "create_ticket", "failure")
        == 1
    )


@pytest.mark.asyncio
async def test_metrics_are_exposed_in_prometheus_format(mcp_metrics: McpMetricsDsl) -> None:
    metrics = await mcp_metrics.private_metrics()

    assert metrics.accessible is True
    assert metrics.prometheus_compatible is True
    assert _has_metric(metrics, INVOCATION_COUNT_METRIC)
    assert _has_metric(metrics, INVOCATION_DURATION_COUNT_METRIC)


@pytest.mark.asyncio
async def test_standard_process_and_runtime_metrics_are_exposed(
    mcp_metrics: McpMetricsDsl,
) -> None:
    metrics = await mcp_metrics.private_metrics()

    assert _has_metric_with_prefix(metrics, "process_")
    assert _has_metric_with_prefix(metrics, "python_")


@pytest.mark.asyncio
async def test_repeated_invocations_accumulate(mcp_metrics: McpMetricsDsl) -> None:
    for _ in range(3):
        await mcp_metrics.complete_invocation("test", "echo", InvocationOutcome.SUCCESS)

    metrics = await mcp_metrics.private_metrics()

    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "test", "echo", "success") == 3
    assert _sample_value(metrics, INVOCATION_DURATION_COUNT_METRIC, "test", "echo", "success") == 3


@pytest.mark.asyncio
async def test_success_and_failure_outcomes_remain_distinct(mcp_metrics: McpMetricsDsl) -> None:
    await mcp_metrics.complete_invocation("test", "echo", InvocationOutcome.SUCCESS)
    await mcp_metrics.complete_invocation("test", "echo", InvocationOutcome.SUCCESS)
    await mcp_metrics.complete_invocation("test", "echo", InvocationOutcome.FAILURE)

    metrics = await mcp_metrics.private_metrics()

    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "test", "echo", "success") == 2
    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "test", "echo", "failure") == 1


@pytest.mark.asyncio
async def test_identically_named_tools_on_different_connectors_remain_distinct(
    mcp_metrics: McpMetricsDsl,
) -> None:
    await mcp_metrics.complete_invocation("primary", "search", InvocationOutcome.SUCCESS)
    await mcp_metrics.complete_invocation("secondary", "search", InvocationOutcome.SUCCESS)

    metrics = await mcp_metrics.private_metrics()

    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "primary", "search", "success") == 1
    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "secondary", "search", "success") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", list(InvocationOutcome))
async def test_metrics_recording_preserves_tool_outcome(
    mcp_metrics: McpMetricsDsl,
    outcome: InvocationOutcome,
) -> None:
    result = await mcp_metrics.complete_invocation("test", "echo", outcome)

    assert result.outcome is outcome


@pytest.mark.asyncio
async def test_metrics_are_reachable_from_private_service_network(
    mcp_metrics: McpMetricsDsl,
) -> None:
    metrics = await mcp_metrics.private_metrics()

    assert metrics.accessible is True
    assert metrics.prometheus_compatible is True


@pytest.mark.asyncio
async def test_metrics_are_not_reachable_through_public_ingress(
    mcp_metrics: McpMetricsDsl,
) -> None:
    metrics = await mcp_metrics.public_metrics()

    assert metrics.accessible is False


@pytest.mark.asyncio
async def test_metrics_expose_only_approved_invocation_labels(
    mcp_metrics: McpMetricsDsl,
) -> None:
    await mcp_metrics.complete_invocation("crm", "create_contact", InvocationOutcome.SUCCESS)

    metrics = await mcp_metrics.private_metrics()
    sample = _sample(metrics, INVOCATION_COUNT_METRIC, "crm", "create_contact", "success")

    assert sample.labels == {
        "connector_name": "crm",
        "tool_name": "create_contact",
        "outcome": "success",
    }


@pytest.mark.asyncio
async def test_invocation_metrics_are_isolated_by_connector_tool_and_outcome(
    mcp_metrics: McpMetricsDsl,
) -> None:
    await mcp_metrics.complete_invocation("github", "search", InvocationOutcome.SUCCESS)
    await mcp_metrics.complete_invocation("github", "create_issue", InvocationOutcome.FAILURE)
    await mcp_metrics.complete_invocation("jira", "search", InvocationOutcome.FAILURE)

    metrics = await mcp_metrics.private_metrics()

    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "github", "search", "success") == 1
    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "github", "create_issue", "failure") == 1
    assert _sample_value(metrics, INVOCATION_COUNT_METRIC, "jira", "search", "failure") == 1


@pytest.mark.asyncio
async def test_invocation_metrics_reset_after_process_restart(mcp_metrics: McpMetricsDsl) -> None:
    await mcp_metrics.complete_invocation("test", "echo", InvocationOutcome.SUCCESS)

    await mcp_metrics.restart_mcp_process()
    metrics = await mcp_metrics.private_metrics()

    assert not _has_sample(metrics, INVOCATION_COUNT_METRIC, "test", "echo", "success")


@pytest.mark.asyncio
async def test_metrics_endpoint_uses_a_port_separate_from_mcp_traffic(
    mcp_metrics: McpMetricsDsl,
) -> None:
    endpoints = await mcp_metrics.service_endpoints()

    assert endpoints.metrics_port != endpoints.mcp_port
    assert endpoints.metrics_path == "/metrics"


def _sample(
    response: MetricsResponse,
    metric_name: str,
    connector_name: str,
    tool_name: str,
    outcome: str,
) -> MetricSample:
    matching_samples = [
        sample
        for sample in response.samples
        if sample.name == metric_name
        and sample.labels.get("connector_name") == connector_name
        and sample.labels.get("tool_name") == tool_name
        and sample.labels.get("outcome") == outcome
    ]
    assert len(matching_samples) == 1
    return matching_samples[0]


def _sample_value(
    response: MetricsResponse,
    metric_name: str,
    connector_name: str,
    tool_name: str,
    outcome: str,
) -> float:
    return _sample(response, metric_name, connector_name, tool_name, outcome).value


def _has_sample(
    response: MetricsResponse,
    metric_name: str,
    connector_name: str,
    tool_name: str,
    outcome: str,
) -> bool:
    return any(
        sample.name == metric_name
        and sample.labels.get("connector_name") == connector_name
        and sample.labels.get("tool_name") == tool_name
        and sample.labels.get("outcome") == outcome
        for sample in response.samples
    )


def _has_metric(response: MetricsResponse, metric_name: str) -> bool:
    return any(sample.name == metric_name for sample in response.samples)


def _has_metric_with_prefix(response: MetricsResponse, prefix: str) -> bool:
    return any(sample.name.startswith(prefix) for sample in response.samples)
