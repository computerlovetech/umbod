from collections import defaultdict
from typing import DefaultDict, Dict, Mapping, Tuple

from pydantic import BaseModel, ConfigDict

from umbod.mcp.metrics.models import CompletedToolInvocation


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
        self._invocation_counts: DefaultDict[Tuple[str, str, str], int] = defaultdict(int)

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        key = (
            invocation.connector_name,
            invocation.tool_name,
            invocation.outcome.value,
        )
        self._invocation_counts[key] += 1

    def metric_samples(self) -> Tuple[McpMetricSample, ...]:
        samples = []
        for (connector_name, tool_name, outcome), count in self._invocation_counts.items():
            labels: Dict[str, str] = {
                "connector_name": connector_name,
                "tool_name": tool_name,
                "outcome": outcome,
            }
            samples.extend(
                (
                    McpMetricSample(
                        name=INVOCATION_COUNT_METRIC,
                        labels=labels,
                        value=float(count),
                    ),
                    McpMetricSample(
                        name=INVOCATION_DURATION_COUNT_METRIC,
                        labels=labels,
                        value=float(count),
                    ),
                )
            )
        return tuple(samples)

    def reset(self) -> None:
        self._invocation_counts.clear()
