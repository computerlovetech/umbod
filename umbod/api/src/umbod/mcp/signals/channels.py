from umbod.core.signals import Signal, SignalFailureHandler
from umbod.mcp.signals.events import McpToolInvocationCompleted, ToolInventoryObserved


class McpSignals:
    def __init__(self, failure_handler: SignalFailureHandler) -> None:
        self._failure_handler = failure_handler
        self.invocation_completed: Signal[McpToolInvocationCompleted] = Signal(failure_handler)
        self.tool_inventory_observed: Signal[ToolInventoryObserved] = Signal(failure_handler)

    def report_failure(self, name: str, error: BaseException) -> None:
        try:
            self._failure_handler.handles(name, error)
        except Exception:
            return
