from typing import Literal, cast, overload

from .classification import (
    ActivityClassification, ClassifiedSkill, ClassifiedTool, classify_activity,
    classify_declared_activity,
)
from .models import (
    Activity, ExtendedActivity, LegacyMappingEvidence, LegacyNormalizedLogRecord, LegacyProducerEvidence,
    MappingEvidence, MissingValue, NormalizedLogRecord, NormalizedRecord, ProducerFields,
    Outcome, PermissionDecision, ProducerEvidence, SkillActivation, SourceEvidence,
    TextEvidence, TextValue, TimestampEvidence, ToolActivity, UnmappedActivity,
)
from .requests import request_activity


Producer = Literal["codex", "claude", "generic"]


def text(value: TextEvidence) -> str:
    return value.value if isinstance(value, TextValue) else ""


def selected_tool(evidence: ProducerFields) -> TextEvidence:
    for alias in evidence.tool_aliases:
        if isinstance(alias.value, TextValue):
            return alias.value
    return MissingValue(kind="missing")


def _producer(source: str, event: str) -> Producer:
    if event.startswith("codex."):
        return "codex"
    if event.startswith("claude_code."):
        return "claude"
    if source in ("codex", "codex_exec"):
        return "codex"
    if source in ("claude-code", "claude-code-desktop"):
        return "claude"
    return "generic"


def _outcome(evidence: ProducerFields, declared: bool) -> Outcome:
    if declared and evidence.declared_outcome.state != "missing":
        state = evidence.declared_outcome.state
        return cast(Outcome, state) if state in ("success", "failure", "unknown") else "unknown"
    success = evidence.success.state
    return "success" if success == "true" else "failure" if success == "false" else "unknown"


def _skill_trigger(evidence: ProducerFields, producer: Producer) -> Literal["explicit", "implicit", "nested", "unknown"]:
    if producer == "codex":
        return evidence.skill_invocation_type
    if producer == "claude":
        return {"user-slash": "explicit", "claude-proactive": "implicit", "nested-skill": "nested"}.get(evidence.skill_trigger, "unknown")
    return evidence.skill_trigger if evidence.skill_trigger in ("explicit", "implicit") else "unknown"


def _classified_activity(classification: ActivityClassification, evidence: ProducerFields, declared: bool, producer: Producer) -> Activity:
    if isinstance(classification, ClassifiedSkill):
        return SkillActivation(kind="skill_activation", trigger=_skill_trigger(evidence, producer))
    if isinstance(classification, ClassifiedTool):
        return ToolActivity(
            kind="tool_result", activity_kind=classification.activity_kind,
            outcome=classification.outcome, tool_name=selected_tool(evidence),
            provenance=evidence.tool_provenance, duration=evidence.duration,
            completion="declared_activity" if declared else "reported_wrapper_result",
        )
    return UnmappedActivity(kind="unmapped")


def _permission_decision(producer: Producer, evidence: ProducerFields) -> PermissionDecision:
    decision = evidence.decision
    normalized: Literal["accept", "reject", "unknown"] = "unknown"
    if producer == "claude" and decision in ("accept", "reject"):
        normalized = cast(Literal["accept", "reject"], decision)
    elif producer == "codex":
        if decision in ("approved", "approved_with_amendment", "approved_for_session", "approved_mcp_policy_amendment", "approved_with_network_policy_allow"):
            normalized = "accept"
        elif decision in ("denied", "abort", "denied_with_network_policy_deny"):
            normalized = "reject"
    return PermissionDecision(kind="permission_decision", decision=normalized, execution="not_asserted")


def _event_activity(source: str, event: str, evidence: LegacyProducerEvidence | ProducerEvidence) -> ExtendedActivity:
    if isinstance(evidence, ProducerEvidence):
        request = request_activity(source, event, evidence)
        if request.kind != "unmapped":
            return request
    if event in ("claude_code.tool_decision", "codex.tool_decision") or (
        source in ("claude-code", "claude-code-desktop") and event == "tool_decision"
    ):
        return _permission_decision(_producer(source, event), evidence)
    classification = classify_activity(source, event, text(selected_tool(evidence)), _outcome(evidence, False), evidence.tool_provenance.origin)
    return _classified_activity(classification, evidence, False, _producer(source, event))


def _activity_identity(activity: ExtendedActivity) -> str:
    return activity.activity_kind if isinstance(activity, ToolActivity) else activity.kind


@overload
def normalize_log(source: SourceEvidence, timestamps: TimestampEvidence, evidence: LegacyProducerEvidence) -> LegacyNormalizedLogRecord: ...


@overload
def normalize_log(source: SourceEvidence, timestamps: TimestampEvidence, evidence: ProducerEvidence) -> NormalizedLogRecord: ...


def normalize_log(source: SourceEvidence, timestamps: TimestampEvidence, evidence: LegacyProducerEvidence | ProducerEvidence) -> NormalizedRecord:
    service = text(source.service)
    semantic = _event_activity(service, text(source.semantic_event), evidence)
    record = _event_activity(service, text(source.record_event), evidence)
    selected = source.semantic_event
    selected_activity = semantic
    if semantic.kind == "unmapped":
        selected, selected_activity = source.record_event, record
    if selected_activity.kind == "unmapped" and isinstance(source.semantic_event, TextValue):
        selected = source.semantic_event
    event = text(selected)
    producer = _producer(service, event)
    declared = _classified_activity(classify_declared_activity(text(evidence.declared_kind), _outcome(evidence, True)), evidence, True, producer)
    activity = selected_activity if declared.kind == "unmapped" else declared
    recognition = "unmapped"
    if declared.kind != "unmapped":
        recognition = "declared"
    elif selected_activity.kind != "unmapped":
        recognition = "qualified_event" if event.startswith(("codex.", "claude_code.")) else "source_gated_event"
    service_producer = _producer(service, "")
    mapping_id = "umbod.activity" if recognition == "declared" else "unmapped" if recognition == "unmapped" else "codex.events" if producer == "codex" else "claude.events"
    mapping = {
        "producer": producer, "mapping_id": mapping_id, "mapping_version": evidence.schema_version,
        "recognition": recognition, "authority": "producer_claim",
        "service_conflict": producer != service_producer and producer != "generic" and service_producer != "generic",
        "declaration_event_conflict": declared.kind != "unmapped" and selected_activity.kind != "unmapped" and _activity_identity(declared) != _activity_identity(selected_activity),
        "event_identity_conflict": semantic.kind != "unmapped" and record.kind != "unmapped" and text(source.semantic_event) != text(source.record_event),
    }
    if isinstance(evidence, LegacyProducerEvidence):
        return LegacyNormalizedLogRecord.model_validate({
            "kind": "normalized", "schema_version": 1, "source": source, "timestamps": timestamps,
            "evidence": evidence, "selected_event": selected, "activity": activity,
            "mapping": LegacyMappingEvidence.model_validate(mapping),
        })
    return NormalizedLogRecord(
        kind="normalized", schema_version=2, source=source, timestamps=timestamps,
        evidence=evidence, selected_event=selected, activity=activity,
        mapping=MappingEvidence.model_validate(mapping),
    )
