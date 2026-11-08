from math import isfinite
from typing import cast

from .decoding import DecodedAttribute, DecodedBoolean, DecodedInteger, DecodedInvalid, DecodedNumber, DecodedString, DecodedValue
from .numeric import capture_fields
from .models import (
    CorrelationEvidence, DurationEvidence, InvalidDuration, InvalidValue, MissingDuration,
    MissingValue, ProducerEvidence, ReportedDuration, ScalarEvidence, TextEvidence,
    TextValue, ToolAlias, ToolProvenance, is_approved_schema_url,
)


LEGACY_KEYS = frozenset((
    "service.name", "event.name", "tool.name", "tool_name", "mcp.tool.name",
    "session.id", "session_id", "conversation.id", "conversation_id", "mcp.session.id",
))
TOOL_KEYS = ("tool.name", "tool_name", "mcp.tool.name")
ORIGIN_KEYS = ("tool_type", "tool.type", "tool_kind", "tool.kind", "tool_origin", "tool_namespace")
EXTERNAL_KEYS = ("mcp_server", "mcp_server_origin", "mcp.server.name", "mcp.tool.name")
CORRELATION_KEYS = (
    "session.id", "session_id", "conversation.id", "conversation_id", "mcp.session.id",
    "turn.id", "turn_id", "prompt.id", "prompt_id", "request.id", "request_id",
    "tool_call.id", "tool_call_id", "call_id", "tool_use_id", "trace_id", "span_id",
    "client_request_id", "auth.request_id",
)


def capture_producer_evidence(decoded: tuple[DecodedAttribute, ...]) -> ProducerEvidence:
    attributes = {attribute.key: attribute.value for attribute in decoded}
    declared = attribute_text(attributes, "umbod.activity.kind")
    if isinstance(declared, TextValue) and declared.value not in ("tool_call", "file_read", "file_edit", "skill_activation"):
        declared = InvalidValue(kind="invalid", reason="unrecognized")
    return ProducerEvidence(
        schema_version=2, fields=capture_fields(attributes), declared_kind=declared, declared_outcome=_scalar(attributes, "umbod.activity.outcome"),
        success=_scalar(attributes, "success"),
        tool_aliases=tuple(ToolAlias.model_validate({"key": key, "value": attribute_text(attributes, key)}) for key in TOOL_KEYS if key in attributes),
        tool_provenance=_provenance(attributes),
        correlations=tuple(CorrelationEvidence.model_validate({"key": key, "value": attribute_text(attributes, key)}) for key in CORRELATION_KEYS if key in attributes),
        duration=_duration(attributes), decision=_category(attributes, "decision", (
            "accept", "reject", "approved", "approved_with_amendment", "approved_for_session",
            "approved_mcp_policy_amendment", "approved_with_network_policy_allow",
            "denied_with_network_policy_deny", "denied", "timed_out", "abort",
        )),
        skill_trigger=_category(attributes, "invocation_trigger", ("user-slash", "claude-proactive", "nested-skill")),
        skill_invocation_type=_category(attributes, "skill.invocation_type", ("explicit", "implicit")),
    )


def text_evidence(value: str) -> TextEvidence:
    return TextValue(kind="text", value=value)


def bounded_text_evidence(value: str) -> TextEvidence:
    if len(value) > 1024:
        return InvalidValue(kind="invalid", reason="oversize")
    return text_evidence(value)


def schema_url_evidence(value: str) -> TextEvidence:
    if not value:
        return MissingValue(kind="missing")
    if len(value) > 1024:
        return InvalidValue(kind="invalid", reason="oversize")
    if not is_approved_schema_url(value):
        return InvalidValue(kind="invalid", reason="unrecognized")
    return TextValue(kind="text", value=value)


def attribute_text(attributes: dict[str, DecodedValue], key: str) -> TextEvidence:
    if key not in attributes:
        return MissingValue(kind="missing")
    value = attributes[key]
    if isinstance(value, DecodedString):
        return text_evidence(value.value) if key in LEGACY_KEYS else bounded_text_evidence(value.value)
    reason = value.reason if isinstance(value, DecodedInvalid) else "wrong_type"
    return InvalidValue(kind="invalid", reason=reason)


def _scalar(attributes: dict[str, DecodedValue], key: str) -> ScalarEvidence:
    if key not in attributes:
        return ScalarEvidence(state="missing", representation="missing", reason="missing")
    value = attributes[key]
    if key == "success" and isinstance(value, DecodedBoolean):
        return ScalarEvidence(state="true" if value.value else "false", representation="boolean", reason="valid")
    if isinstance(value, DecodedString):
        allowed = ("true", "false") if key == "success" else ("success", "failure", "unknown")
        if value.value in allowed:
            return ScalarEvidence.model_validate({"state": value.value, "representation": "string", "reason": "valid"})
        return ScalarEvidence(state="invalid", representation="string", reason="unrecognized")
    return ScalarEvidence(state="invalid", representation="invalid", reason=value.reason if isinstance(value, DecodedInvalid) else "wrong_type")


def _provenance(attributes: dict[str, DecodedValue]) -> ToolProvenance:
    external = any(
        (isinstance(value := attributes.get(key), DecodedBoolean) and key != "mcp.tool.name" and value.value)
        or (isinstance(value, DecodedString) and bool(value.value.strip()))
        for key in EXTERNAL_KEYS
    )
    external = external or any(isinstance(value := attribute_text(attributes, key), TextValue) and value.value in ("mcp", "custom") for key in ORIGIN_KEYS)
    namespace = attribute_text(attributes, "tool_namespace")
    category = namespace.value if isinstance(namespace, TextValue) and namespace.value in ("mcp", "custom", "native", "functions") else "missing" if isinstance(namespace, MissingValue) else "unknown"
    explicit_native = any(isinstance(value := attribute_text(attributes, key), TextValue) and value.value == "native" for key in ORIGIN_KEYS)
    return ToolProvenance.model_validate({
        "origin": "external" if external else "native",
        "basis": "explicit" if external or explicit_native else "assumed",
        "namespace": category, "external_indicator": external,
    })


def _duration(attributes: dict[str, DecodedValue]) -> DurationEvidence:
    for key, unit in (("duration_ms", "milliseconds"), ("duration_ms_total", "milliseconds"), ("duration", "milliseconds"), ("duration_seconds", "seconds"), ("duration_ns", "nanoseconds")):
        if key not in attributes:
            continue
        value = attributes[key]
        if key != "duration_ms":
            return InvalidDuration(kind="invalid", reason="unrecognized")
        if not isinstance(value, (DecodedString, DecodedNumber, DecodedInteger)):
            return InvalidDuration(kind="invalid", reason=value.reason if isinstance(value, DecodedInvalid) else "wrong_type")
        try:
            number = float(value.value)
        except (ValueError, OverflowError):
            return InvalidDuration(kind="invalid", reason="unrecognized")
        if not isfinite(number) or number < 0:
            return InvalidDuration(kind="invalid", reason="out_of_range")
        return ReportedDuration.model_validate({"kind": "reported", "value": number, "unit": unit})
    return MissingDuration(kind="missing")


def _category(attributes: dict[str, DecodedValue], key: str, allowed: tuple[str, ...]) -> str:
    value = attribute_text(attributes, key)
    return cast(str, value.value) if isinstance(value, TextValue) and value.value in allowed else "unknown"
