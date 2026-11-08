from collections.abc import Mapping

from umbod.core.telemetry.normalization.classification import (
    ActivityClassification,
    ClassifiedSkill,
    ClassifiedTool,
    ToolOrigin as ToolOrigin,
    classify_activity as classify_canonical_activity,
    classify_declared_activity as classify_canonical_declared_activity,
)
from umbod.core.telemetry.normalization.models import Outcome as ActivityOutcome

from .models import LogDimension


def _dimensions(classification: ActivityClassification) -> Mapping[LogDimension, str]:
    if isinstance(classification, ClassifiedTool):
        return {
            LogDimension.ACTIVITY_KIND: classification.activity_kind,
            LogDimension.OUTCOME: classification.outcome,
        }
    if isinstance(classification, ClassifiedSkill):
        return {LogDimension.ACTIVITY_KIND: "skill_activation"}
    return {}


def classify_declared_activity(kind: str, outcome: ActivityOutcome) -> Mapping[LogDimension, str]:
    return _dimensions(classify_canonical_declared_activity(kind, outcome))


def classify_activity(
    source: str,
    event: str,
    tool: str,
    outcome: ActivityOutcome,
    tool_origin: ToolOrigin,
) -> Mapping[LogDimension, str]:
    return _dimensions(classify_canonical_activity(source, event, tool, outcome, tool_origin))
