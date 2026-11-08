import pytest

from umbod.core.telemetry.analytics import LogDimension
from umbod.core.telemetry.analytics.activity import (
    ActivityOutcome,
    ToolOrigin,
    classify_activity,
    classify_declared_activity,
)


@pytest.mark.parametrize("source,event,tool,expected", [
    ("custom", "claude_code.tool_result", "Read", "file_read"),
    ("claude-code", "tool_result", "Edit", "file_edit"),
    ("claude-code-desktop", "tool_result", "Write", "file_edit"),
    ("claude-code", "tool_result", "Skill", "tool_call"),
    ("claude-code", "tool_result", "MultiEdit", "tool_call"),
    ("claude-code", "tool_result", "NotebookEdit", "tool_call"),
    ("claude-code", "tool_result", "read", "tool_call"),
    ("custom", "codex.tool_result", "apply_patch", "file_edit"),
    ("codex", "tool_result", "apply_patch", "file_edit"),
    ("codex", "codex.tool_result", "exec_command", "tool_call"),
    ("codex", "codex.tool_result", "shell", "tool_call"),
    ("custom", "codex.skill_invocation", "", "skill_activation"),
    ("custom", "claude_code.skill_activated", "", "skill_activation"),
    ("claude-code-desktop", "skill_activated", "", "skill_activation"),
])
def test_recognized_completions_have_exactly_one_activity(
    source: str, event: str, tool: str, expected: str,
) -> None:
    result = classify_activity(source, event, tool, "unknown", "native")
    assert result == (
        {LogDimension.ACTIVITY_KIND: expected}
        if expected == "skill_activation"
        else {LogDimension.ACTIVITY_KIND: expected, LogDimension.OUTCOME: "unknown"}
    )


@pytest.mark.parametrize("source,event", [
    ("custom", "tool_result"), ("Claude-Code", "tool_result"),
    ("custom", "skill_activated"), ("codex", "skill_invocation"),
    ("claude-code", "tool_start"), ("", ""),
    ("codex_exec", "event otel/src/events/session_telemetry.rs:375"),
    ("codex_exec", "event otel/src/events/session_telemetry.rs:412"),
    ("codex_exec", "event otel/src/metrics.rs:90"),
    ("codex_exec", "event core/src/provider.rs:120"),
    ("ui-check", "tool_result"),
    ("ui-check", "synthetic"),
])
def test_unrecognized_events_remain_unenriched(source: str, event: str) -> None:
    assert classify_activity(source, event, "Read", "unknown", "unknown") == {}


@pytest.mark.parametrize("tool_origin", ["external", "unknown"])
def test_codex_name_collision_or_unknown_provenance_remains_generic_tool_call(
    tool_origin: ToolOrigin,
) -> None:
    assert classify_activity(
        "custom", "codex.tool_result", "apply_patch", "failure", tool_origin,
    ) == {LogDimension.ACTIVITY_KIND: "tool_call", LogDimension.OUTCOME: "failure"}


@pytest.mark.parametrize("tool,expected", [("Read", "file_read"), ("Edit", "file_edit"), ("Write", "file_edit")])
def test_claude_exact_native_names_remain_classifiable_with_unknown_history(
    tool: str, expected: str,
) -> None:
    assert classify_activity(
        "claude-code", "tool_result", tool, "unknown", "unknown",
    ) == {LogDimension.ACTIVITY_KIND: expected, LogDimension.OUTCOME: "unknown"}


@pytest.mark.parametrize("kind", ["tool_call", "file_read", "file_edit", "skill_activation"])
@pytest.mark.parametrize("outcome", ["success", "failure", "unknown"])
def test_declared_activity_preserves_exact_kind_and_tool_outcome(
    kind: str, outcome: ActivityOutcome,
) -> None:
    expected = {LogDimension.ACTIVITY_KIND: kind}
    if kind != "skill_activation":
        expected[LogDimension.OUTCOME] = outcome
    assert classify_declared_activity(kind, outcome) == expected


@pytest.mark.parametrize("kind", ["", "File_read", "file_read ", "read", "tool_result"])
def test_invalid_declared_activity_has_no_mapping(kind: str) -> None:
    assert classify_declared_activity(kind, "success") == {}


def test_explicitly_external_claude_tool_cannot_promote_a_native_name_collision() -> None:
    assert classify_activity(
        "claude-code", "tool_result", "Read", "success", "external",
    ) == {LogDimension.ACTIVITY_KIND: "tool_call", LogDimension.OUTCOME: "success"}
