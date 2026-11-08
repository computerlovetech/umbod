import pytest
from pydantic import ValidationError

from umbod.core.telemetry.normalization import NormalizedLogRecord
from umbod.core.telemetry.normalization.decoding import DecodedAttribute, DecodedBoolean, DecodedString
from umbod.core.telemetry.normalization.evidence import capture_producer_evidence
from umbod.core.telemetry.normalization.mapping import normalize_log
from umbod.core.telemetry.normalization.models import (
    MissingValue, SourceEvidence, TextValue, TimestampEvidence, ToolActivity,
)
from umbod.core.telemetry.analytics.projection import project_analytics_log


def _source(semantic: str, record: str) -> SourceEvidence:
    missing = MissingValue(kind="missing")
    return SourceEvidence(
        service=TextValue(kind="text", value="codex"), service_version=missing, app_version=missing,
        scope_name=missing, scope_version=missing, resource_schema_url=missing, scope_schema_url=missing,
        record_event=TextValue(kind="text", value=record), semantic_event=TextValue(kind="text", value=semantic),
        severity_text=TextValue(kind="text", value="ERROR"), severity_number=17,
    )


def _timestamps() -> TimestampEvidence:
    return TimestampEvidence(source_ns=1001, observed_ns=2002, receipt_ns=3003, effective_source="source")


def test_public_source_evidence_mapper_replays_without_transport_or_analytics_inputs() -> None:
    evidence = capture_producer_evidence((
        DecodedAttribute(key="success", value=DecodedString(kind="string", value="false")),
        DecodedAttribute(key="tool_name", value=DecodedString(kind="string", value="apply_patch")),
        DecodedAttribute(key="duration_ms", value=DecodedString(kind="string", value="42")),
    ))
    normalized = normalize_log(_source("codex.tool_result", "metadata"), _timestamps(), evidence)
    restored = NormalizedLogRecord.model_validate_json(normalized.model_dump_json())
    assert normalize_log(restored.source, restored.timestamps, restored.evidence) == normalized
    assert project_analytics_log(restored).normalization == normalized
    assert isinstance(normalized.activity, ToolActivity)
    assert normalized.activity.activity_kind == "file_edit"
    assert normalized.activity.outcome == "failure"
    assert normalized.activity.completion == "reported_wrapper_result"


def test_present_invalid_canonical_outcome_blocks_success_fallback_for_declaration() -> None:
    evidence = capture_producer_evidence((
        DecodedAttribute(key="umbod.activity.kind", value=DecodedString(kind="string", value="tool_call")),
        DecodedAttribute(key="umbod.activity.outcome", value=DecodedBoolean(kind="boolean", value=True)),
        DecodedAttribute(key="success", value=DecodedBoolean(kind="boolean", value=True)),
    ))
    normalized = normalize_log(_source("", ""), _timestamps(), evidence)
    assert isinstance(normalized.activity, ToolActivity)
    assert normalized.activity.outcome == "unknown"
    assert normalized.mapping.producer == "codex"
    assert normalized.mapping.mapping_id == "umbod.activity"
    assert normalized.mapping.authority == "producer_claim"


def test_recognized_semantic_permission_prevents_raw_event_execution_inference() -> None:
    evidence = capture_producer_evidence((DecodedAttribute(key="decision", value=DecodedString(kind="string", value="approved")),))
    normalized = normalize_log(_source("codex.tool_decision", "codex.tool_result"), _timestamps(), evidence)
    assert normalized.activity.kind == "permission_decision"
    assert normalized.mapping.event_identity_conflict is True


@pytest.mark.parametrize("semantic,record,expected", [
    ("diagnostic", "codex.tool_decision", "permission_decision"),
    ("codex.tool_result", "codex.tool_decision", "tool_result"),
    ("codex.skill_invocation", "codex.tool_result", "skill_activation"),
])
def test_recognized_semantic_event_precedes_all_raw_event_variants(semantic: str, record: str, expected: str) -> None:
    normalized = normalize_log(_source(semantic, record), _timestamps(), capture_producer_evidence(()))
    assert normalized.activity.kind == expected


def test_declared_activity_retains_producer_identity_and_reports_event_disagreement() -> None:
    evidence = capture_producer_evidence((DecodedAttribute(key="umbod.activity.kind", value=DecodedString(kind="string", value="file_read")),))
    normalized = normalize_log(_source("codex.skill_invocation", "metadata"), _timestamps(), evidence)
    assert normalized.mapping.producer == "codex"
    assert normalized.mapping.declaration_event_conflict is True
    assert normalized.mapping.event_identity_conflict is False


def test_normalized_models_are_immutable_and_reject_unknown_fields() -> None:
    normalized = normalize_log(_source("codex.tool_result", "metadata"), _timestamps(), capture_producer_evidence(()))
    with pytest.raises(ValidationError):
        normalized.schema_version = 2
    with pytest.raises(ValidationError):
        NormalizedLogRecord.model_validate({**normalized.model_dump(), "unapproved": "private"})
