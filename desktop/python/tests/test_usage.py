from types import SimpleNamespace
from typing import Any

import pytest
from fakes import MemoryState
from umbod.hosting import McpToolInvocationLogSink

from umbod_desktop.backend_integration.usage import DesktopUsageSink
from umbod_desktop.contracts import InvocationCompletion
from umbod_desktop.ports import InvocationRecorder
from umbod_desktop.usage import DesktopUsageRecorder


class MemoryRecorder:
    def __init__(self) -> None:
        self.completions: list[InvocationCompletion] = []

    def record(self, completion: InvocationCompletion) -> None:
        self.completions.append(completion)


@pytest.mark.parametrize("connector,operation,category,outcome,expected", [
    ("connector", "read", "", "success", "success"),
    ("connector", "read", "connector_error", "failure", "failure"),
    ("connector", "read", "authorization", "failure", ""),
    ("connector", "read", "validation", "failure", ""),
    (None, "search_tools", "", "success", ""),
    ("connector", None, "", "success", ""),
])
def test_invocation_sink_filters_before_mapping(
    connector: str | None, operation: str | None, category: str, outcome: str, expected: str,
) -> None:
    recorder = MemoryRecorder()
    sink: McpToolInvocationLogSink = DesktopUsageSink(recorder)
    event = SimpleNamespace(
        started=SimpleNamespace(tool=SimpleNamespace(connector_id=connector, operation_name=operation)),
        outcome=outcome, failure_category=category,
        arguments={"secret": "not recorded"}, result="not recorded",
    )
    sink.record_invocation_completed(event)
    assert [completion.outcome for completion in recorder.completions] == ([expected] if expected else [])
    if expected:
        assert recorder.completions[0].model_dump() == {
            "connector_id": "connector", "operation_name": "read", "outcome": expected,
        }


def test_recorder_updates_existing_counts_and_daily_totals(monkeypatch: Any) -> None:
    monkeypatch.setattr("umbod_desktop.usage.time.time", lambda: 86400 * 200)
    state = MemoryState({"tool_usage": {"connector.read": {"succeeded": 3, "failed": 2}}})
    recorder: InvocationRecorder = DesktopUsageRecorder(state)
    recorder.record(InvocationCompletion(connector_id="connector", operation_name="read", outcome="success"))
    recorder.record(InvocationCompletion(connector_id="connector", operation_name="read", outcome="failure"))
    assert state.data == {
        "tool_usage": {"connector.read": {"succeeded": 4, "failed": 3}},
        "daily_calls": {"200": 2}, "daily_tracking_started": 200,
    }
    assert state.saves == 2
