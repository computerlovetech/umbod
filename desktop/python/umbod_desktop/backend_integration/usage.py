from umbod.hosting import McpToolInvocationLogEvent

from ..contracts import InvocationCompletion
from ..ports import InvocationRecorder


class DesktopUsageSink:
    def __init__(self, recorder: InvocationRecorder) -> None:
        self.recorder = recorder

    def record_invocation_completed(self, event: McpToolInvocationLogEvent) -> None:
        tool = event.started.tool
        if tool.connector_id is None or tool.operation_name is None:
            return
        if getattr(event, "failure_category", None) in ("authorization", "validation"):
            return
        self.recorder.record(InvocationCompletion(
            connector_id=tool.connector_id,
            operation_name=tool.operation_name,
            outcome="success" if event.outcome == "success" else "failure",
        ))
