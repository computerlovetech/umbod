from datetime import datetime, timedelta, timezone

from umbod.core.telemetry.normalization.mapping import selected_tool
from umbod.core.telemetry.normalization.models import MissingValue, NormalizedRecord, SkillActivation, TextValue, ToolActivity

from .models import DimensionGroup, LogDimension, PresentDimensionValue
from .write_models import AnalyticsLogRecord, UnownedLog


def project_analytics_log(record: NormalizedRecord) -> AnalyticsLogRecord:
    source = record.source
    values: dict[LogDimension, str] = {}
    candidates = (
        (LogDimension.SOURCE, source.service),
        (LogDimension.EVENT_NAME, source.record_event if isinstance(source.record_event, TextValue) and source.record_event.value else source.semantic_event),
        (LogDimension.SESSION_ID, next((item.value for item in record.evidence.correlations if item.key in ("session.id", "session_id", "conversation.id", "conversation_id", "mcp.session.id") and isinstance(item.value, TextValue)), MissingValue(kind="missing"))),
        (LogDimension.TOOL_NAME, selected_tool(record.evidence)),
        (LogDimension.SEVERITY, source.severity_text),
    )
    for dimension, value in candidates:
        if isinstance(value, TextValue) and (dimension != LogDimension.SEVERITY or value.value):
            values[dimension] = value.value
    activity = record.activity
    if isinstance(activity, ToolActivity):
        values[LogDimension.ACTIVITY_KIND] = activity.activity_kind
        values[LogDimension.OUTCOME] = activity.outcome
    elif isinstance(activity, SkillActivation):
        values[LogDimension.ACTIVITY_KIND] = "skill_activation"
    timestamps = record.timestamps
    timestamp = timestamps.source_ns or timestamps.observed_ns or timestamps.receipt_ns
    occurred_at = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=timestamp // 1000)
    return AnalyticsLogRecord(
        occurred_at=occurred_at, owner=UnownedLog(kind="unowned"), normalization=record,
        dimensions=tuple(DimensionGroup(dimension=dimension, value=PresentDimensionValue(kind="present", value=value)) for dimension, value in values.items()),
    )
