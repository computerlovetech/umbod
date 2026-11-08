from collections.abc import Mapping
from typing import Literal

from .models import LogDimension

ActivityOutcome = Literal["success", "failure", "unknown"]
ToolOrigin = Literal["native", "external", "unknown"]


def classify_activity(
    source: str,
    event: str,
    tool: str,
    outcome: ActivityOutcome,
    tool_origin: ToolOrigin,
) -> Mapping[LogDimension, str]:
    claude_tool = event == "claude_code.tool_result" or (
        source in ("claude-code", "claude-code-desktop") and event == "tool_result"
    )
    codex_tool = event == "codex.tool_result" or (
        source == "codex" and event == "tool_result"
    )
    if claude_tool or codex_tool:
        kind = "tool_call"
        if claude_tool and tool == "Read" and tool_origin != "external":
            kind = "file_read"
        elif claude_tool and tool in ("Edit", "Write") and tool_origin != "external":
            kind = "file_edit"
        elif codex_tool and tool == "apply_patch" and tool_origin == "native":
            kind = "file_edit"
        return {LogDimension.ACTIVITY_KIND: kind, LogDimension.OUTCOME: outcome}
    if event in ("claude_code.skill_activated", "codex.skill_invocation") or (
        source in ("claude-code", "claude-code-desktop") and event == "skill_activated"
    ):
        return {LogDimension.ACTIVITY_KIND: "skill_activation"}
    return {}
