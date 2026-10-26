from prometheus_client import CollectorRegistry, Counter, GCCollector, Histogram
from prometheus_client import PlatformCollector, ProcessCollector, generate_latest

from umbod.mcp.metrics.models import (
    CompletedToolInvocation,
    InvocationOutcome,
    InvocationScope,
    ToolInvocationMetricIdentity,
)


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

        self._requests = Counter(
            "umbod_mcp_tool_requests_total",
            "Completed MCP tool requests",
            ("tool_name", "outcome"),
            registry=self._registry,
        )
        self._request_duration = Histogram(
            "umbod_mcp_tool_request_duration_seconds",
            "Completed MCP tool request duration in seconds",
            ("tool_name", "outcome"),
            registry=self._registry,
        )
        self._families = {
            InvocationScope.CONNECTOR: (self._invocations, self._invocation_duration),
            InvocationScope.REQUEST: (self._requests, self._request_duration),
        }

    def initialize_invocation(self, identity: ToolInvocationMetricIdentity) -> None:
        counter, histogram = self._families[identity.scope]
        for outcome in InvocationOutcome:
            labels = self._labels(identity.scope, identity.connector_name, identity.tool_name, outcome)
            counter.labels(**labels)
            histogram.labels(**labels)

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None:
        self.initialize_invocation(ToolInvocationMetricIdentity(
            scope=invocation.scope,
            connector_name=invocation.connector_name,
            tool_name=invocation.tool_name,
        ))
        labels = self._labels(
            invocation.scope, invocation.connector_name, invocation.tool_name, invocation.outcome
        )
        counter, histogram = self._families[invocation.scope]
        counter.labels(**labels).inc()
        histogram.labels(**labels).observe(invocation.duration_seconds)

    @staticmethod
    def _labels(
        scope: InvocationScope, connector_name: str, tool_name: str, outcome: InvocationOutcome
    ) -> dict[str, str]:
        labels = {"tool_name": tool_name, "outcome": outcome.value}
        if scope == InvocationScope.CONNECTOR:
            labels["connector_name"] = connector_name
        return labels

    def prometheus_text(self) -> bytes:
        return generate_latest(self._registry)
