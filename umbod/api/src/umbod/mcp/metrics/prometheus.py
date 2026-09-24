from prometheus_client import CollectorRegistry, Counter, GCCollector, Histogram
from prometheus_client import PlatformCollector, ProcessCollector, generate_latest

from umbod.mcp.metrics.models import CompletedToolInvocation


INVOCATION_LABELS = ("connector_name", "tool_name", "outcome")


class PrometheusMcpMetricsRecorder:
    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        ProcessCollector(registry=self._registry)
        PlatformCollector(registry=self._registry)
        GCCollector(registry=self._registry)
        self._invocations = Counter(
            "umbod_mcp_tool_invocations_total",
            "Completed MCP connector tool invocations",
            INVOCATION_LABELS,
            registry=self._registry,
        )
        self._invocation_duration = Histogram(
            "umbod_mcp_tool_invocation_duration_seconds",
            "Completed MCP connector tool invocation duration in seconds",
            INVOCATION_LABELS,
            registry=self._registry,
        )

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        labels = {
            "connector_name": invocation.connector_name,
            "tool_name": invocation.tool_name,
            "outcome": invocation.outcome.value,
        }
        self._invocations.labels(**labels).inc()
        self._invocation_duration.labels(**labels).observe(invocation.duration_seconds)

    def prometheus_text(self) -> bytes:
        return generate_latest(self._registry)
