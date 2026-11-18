from prometheus_client import CollectorRegistry, Counter, GCCollector, Histogram
from prometheus_client import PlatformCollector, ProcessCollector, generate_latest

from umbod.mcp.metrics.models import (
    CompletedToolInvocation,
    InvocationOutcome,
    InvocationScope,
    ToolInvocationMetricIdentity,
)
from umbod.mcp.metrics.protocol_models import CompletedProtocolRequest, SuccessfulToolsList


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
        self._protocol_duration = Histogram(
            "umbod_mcp_protocol_request_duration_seconds",
            "Completed MCP protocol request duration in seconds",
            ("method", "outcome"),
            registry=self._registry,
        )
        self._tools_list_count = Histogram(
            "umbod_mcp_tools_list_tool_count",
            "Tool count returned by successful MCP tools/list requests",
            buckets=(0, 1, 5, 10, 25, 50, 100, 250, 500, 1000),
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

    def record_protocol_request(self, observation: CompletedProtocolRequest) -> None:
        self._protocol_duration.labels(
            method=observation.method.value, outcome=observation.outcome.value,
        ).observe(observation.duration_seconds)

    def record_tools_list(self, observation: SuccessfulToolsList) -> None:
        self._tools_list_count.observe(observation.tool_count)

    def prometheus_text(self) -> bytes:
        return generate_latest(self._registry)
