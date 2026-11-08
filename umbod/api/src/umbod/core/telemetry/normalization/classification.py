from typing import Annotated, Literal, cast

from pydantic import Field

from .models import ActivityKind, NormalizationModel, Outcome


ToolOrigin = Literal["native", "external", "unknown"]


class ClassifiedTool(NormalizationModel):
    kind: Literal["tool"]
    activity_kind: ActivityKind
    outcome: Outcome


class ClassifiedSkill(NormalizationModel):
    kind: Literal["skill"]


class UnmappedClassification(NormalizationModel):
    kind: Literal["unmapped"]


ActivityClassification = Annotated[ClassifiedTool | ClassifiedSkill | UnmappedClassification, Field(discriminator="kind")]


def classify_declared_activity(kind: str, outcome: Outcome) -> ActivityClassification:
    if kind in ("tool_call", "file_read", "file_edit"):
        return ClassifiedTool(kind="tool", activity_kind=cast(ActivityKind, kind), outcome=outcome)
    if kind == "skill_activation":
        return ClassifiedSkill(kind="skill")
    return UnmappedClassification(kind="unmapped")


def classify_activity(source: str, event: str, tool: str, outcome: Outcome, tool_origin: ToolOrigin) -> ActivityClassification:
    claude_tool = event == "claude_code.tool_result" or (
        source in ("claude-code", "claude-code-desktop") and event == "tool_result"
    )
    codex_tool = event == "codex.tool_result" or (
        source == "codex" and event == "tool_result"
    )
    if claude_tool or codex_tool:
        kind: ActivityKind = "tool_call"
        if claude_tool and tool == "Read" and tool_origin != "external":
            kind = "file_read"
        elif claude_tool and tool in ("Edit", "Write") and tool_origin != "external":
            kind = "file_edit"
        elif codex_tool and tool == "apply_patch" and tool_origin == "native":
            kind = "file_edit"
        return ClassifiedTool(kind="tool", activity_kind=kind, outcome=outcome)
    if event in ("claude_code.skill_activated", "codex.skill_invocation") or (
        source in ("claude-code", "claude-code-desktop") and event == "skill_activated"
    ):
        return ClassifiedSkill(kind="skill")
    return UnmappedClassification(kind="unmapped")
