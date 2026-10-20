import time

from .contracts import InvocationCompletion
from .ports import MetadataState


class DesktopUsageRecorder:
    def __init__(self, state: MetadataState) -> None:
        self.state = state

    def record(self, completion: InvocationCompletion) -> None:
        identity = f"{completion.connector_id}.{completion.operation_name}"
        usage = self.state.data.setdefault("tool_usage", {}).setdefault(
            identity, {"succeeded": 0, "failed": 0}
        )
        usage["succeeded" if completion.outcome == "success" else "failed"] += 1
        day = str(int(time.time()) // 86400)
        daily = self.state.data.setdefault("daily_calls", {})
        daily[day] = daily.get(day, 0) + 1
        self.state.data.setdefault("daily_tracking_started", int(day))
        self.state.save()
