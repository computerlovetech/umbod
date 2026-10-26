from collections import defaultdict
from typing import DefaultDict, Dict, Mapping, Tuple

from pydantic import BaseModel, ConfigDict

from umbod.mcp.metrics.models import (
    CompletedToolInvocation,
    InvocationOutcome,
    InvocationScope,
    ToolInvocationMetricIdentity,
)


INVOCATION_COUNT_METRIC = "umbod_mcp_tool_invocations_total"
INVOCATION_DURATION_COUNT_METRIC = (
    "umbod_mcp_tool_invocation_duration_seconds_count"
)


class McpMetricSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    labels: Mapping[str, str]
    value: float


class InMemoryMcpMetricsRecorder:
    def __init__(self) -> None:
        self._invocation_counts: DefaultDict[
            Tuple[InvocationScope, str, str, str], int
        ] = defaultdict(int)

    def initialize_invocation(self, identity: ToolInvocationMetricIdentity) -> None:
        connector_name = (
            identity.connector_name if identity.scope == InvocationScope.CONNECTOR else ""
        )
        for outcome in InvocationOutcome:
            self._invocation_counts.setdefault(
                (identity.scope, connector_name, identity.tool_name, outcome.value), 0
            )

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.initialize_invocation(ToolInvocationMetricIdentity(
            scope=invocation.scope,
            connector_name=invocation.connector_name,
            tool_name=invocation.tool_name,
        ))
        connector_name = (
            invocation.connector_name if invocation.scope == InvocationScope.CONNECTOR else ""
        )
        key = (
            invocation.scope,
            connector_name,
            invocation.tool_name,
            invocation.outcome.value,
        )
        self._invocation_counts[key] += 1

    def metric_samples(self) -> Tuple[McpMetricSample, ...]:
        samples = []
        for (scope, connector_name, tool_name, outcome), count in self._invocation_counts.items():
            labels: Dict[str, str] = {"tool_name": tool_name, "outcome": outcome}
            count_metric = "umbod_mcp_tool_requests_total"
            duration_count_metric = "umbod_mcp_tool_request_duration_seconds_count"
            if scope == InvocationScope.CONNECTOR:
                labels["connector_name"] = connector_name
                count_metric = INVOCATION_COUNT_METRIC
                duration_count_metric = INVOCATION_DURATION_COUNT_METRIC
            samples.extend(
                (
                    McpMetricSample(
                        name=count_metric,
                        labels=labels,
                        value=float(count),
                    ),
                    McpMetricSample(
                        name=duration_count_metric,
                        labels=labels,
                        value=float(count),
                    ),
                )
            )
        return tuple(samples)

    def reset(self) -> None:
        self._invocation_counts.clear()
