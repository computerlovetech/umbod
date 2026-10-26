from dataclasses import replace
from weakref import WeakSet

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import InvocationFailureEvidence
from umbod.mcp.signals.channels import McpSignals
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory, ToolInventoryObserved
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle


class McpInvocationPublisher:
    def __init__(self, signals: McpSignals) -> None:
        self._signals = signals
        self._completed: WeakSet[McpToolInvocationLifecycle] = WeakSet()

    def report_failure(self, name: str, error: Exception) -> None:
        self._signals.report_failure(name, error)

    def tool_registered(self, identity: McpToolIdentity) -> None:
        self._signals.tool_inventory_observed.send(ToolInventoryObserved((identity,)))

    def start(self, identity: McpToolIdentity) -> McpToolInvocationLifecycle | None:
        try:
            return McpToolInvocationLifecycle.start(identity)
        except Exception as error:
            self._signals.report_failure("MCP tool invocation lifecycle start failed", error)
            return None

    def succeeded(self, lifecycle: McpToolInvocationLifecycle | None) -> None:
        if lifecycle is None or lifecycle in self._completed:
            return
        self._completed.add(lifecycle)
        try:
            completed = lifecycle.succeeded()
        except Exception as error:
            self._signals.report_failure("MCP tool invocation success completion failed", error)
            return
        self._signals.invocation_completed.send(completed)

    def failed(self, lifecycle: McpToolInvocationLifecycle | None, category: McpToolInvocationFailureCategory, diagnostic: InvocationFailureDiagnostic | None, evidence: InvocationFailureEvidence) -> None:
        if lifecycle is None or lifecycle in self._completed:
            return
        self._completed.add(lifecycle)
        try:
            completed = replace(lifecycle.failed(category), diagnostic=diagnostic, evidence=evidence)
        except Exception as error:
            self._signals.report_failure("MCP tool invocation failure completion failed", error)
            return
        self._signals.invocation_completed.send(completed)

