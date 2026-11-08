import json
from decimal import localcontext
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from umbod.core.telemetry.analytics.models import LogDimension
from umbod.core.telemetry.analytics.projection import project_analytics_log
from umbod.core.telemetry.normalization import (
    LegacyNormalizedLogRecord, NormalizationEvidence, NormalizedLogRecord, ProducerEvidence,
)
from umbod.core.telemetry.normalization.decoding import (
    DecodedAttribute, DecodedBoolean, DecodedInteger, DecodedInvalid, DecodedNumber, DecodedString,
)
from umbod.core.telemetry.normalization.evidence import capture_producer_evidence
from umbod.core.telemetry.normalization.mapping import normalize_log
from umbod.core.telemetry.normalization.models import (
    InvalidValue, MissingValue, ModelRequest, ProducerFieldKey, ReportedDecimal,
    ReportedDuration, ReportedInteger, ResponseUsage, SourceEvidence, StreamDiagnostic,
    TextValue, TimestampEvidence, TurnCost,
)


def _source(service: str, semantic: str, record: str) -> SourceEvidence:
    missing = MissingValue(kind="missing")
    return SourceEvidence(
        service=TextValue(kind="text", value=service), service_version=missing, app_version=missing,
        scope_name=missing, scope_version=missing, resource_schema_url=missing, scope_schema_url=missing,
        record_event=TextValue(kind="text", value=record), semantic_event=TextValue(kind="text", value=semantic),
        severity_text=missing, severity_number=0,
    )


def _normalize(event: str, attributes: tuple[DecodedAttribute, ...]) -> NormalizedLogRecord:
    return normalize_log(
        _source("generic", event, ""),
        TimestampEvidence(source_ns=1, observed_ns=0, receipt_ns=2, effective_source="source"),
        capture_producer_evidence(attributes),
    )


def _string(key: ProducerFieldKey, value: str) -> DecodedAttribute:
    return DecodedAttribute(key=key, value=DecodedString(kind="string", value=value))


def _integer(key: ProducerFieldKey, value: int) -> DecodedAttribute:
    return DecodedAttribute(key=key, value=DecodedInteger(kind="integer", value=value))


def test_claude_input_excludes_cache_and_lifetime_breakdowns_are_not_added() -> None:
    normalized = _normalize("claude_code.api_request", (
        _integer("input_tokens", 100), _integer("output_tokens", 20),
        _integer("cache_read_tokens", 80), _integer("cache_creation_tokens", 30),
        _integer("cache_creation_5m_tokens", 0), _integer("cache_creation_1h_tokens", 0),
        _string("model", "claude-sonnet-4-6"), _string("speed", "fast"), _string("effort", "xhigh"),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    usage = normalized.activity.usage
    assert usage.inclusive_input == ReportedInteger(kind="integer", value=210, representation="integer")
    assert usage.derived_total == ReportedInteger(kind="integer", value=230, representation="integer")
    assert usage.cache_creation_5m == ReportedInteger(kind="integer", value=0, representation="integer")
    assert usage.cache_creation_1h == ReportedInteger(kind="integer", value=0, representation="integer")
    assert usage.reported_total.kind == usage.reasoning.kind == "missing"
    assert usage.input_accounting == "excludes_cache"
    assert usage.zero_authority == "producer_report_only"
    restored = NormalizedLogRecord.model_validate_json(normalized.model_dump_json())
    assert normalize_log(restored.source, restored.timestamps, restored.evidence) == normalized


def test_missing_invalid_and_zero_remain_distinct_and_prevent_partial_derived_total() -> None:
    normalized = _normalize("claude_code.api_request", (
        _integer("input_tokens", 0), _integer("output_tokens", 10),
        DecodedAttribute(key="cache_read_tokens", value=DecodedBoolean(kind="boolean", value=False)),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    usage = normalized.activity.usage
    assert usage.input == ReportedInteger(kind="integer", value=0, representation="integer")
    assert usage.cache_read.kind == "invalid"
    assert usage.cache_creation.kind == "missing"
    assert usage.inclusive_input.kind == usage.derived_total.kind == "invalid"
    missing = _normalize("claude_code.api_request", (_integer("input_tokens", 0),))
    assert isinstance(missing.activity, ModelRequest)
    assert missing.activity.usage.inclusive_input.kind == "missing"


@pytest.mark.parametrize("value", [
    DecodedBoolean(kind="boolean", value=True),
    DecodedInteger(kind="integer", value=-1),
    DecodedInteger(kind="integer", value=9223372036854775808),
    DecodedNumber(kind="number", value=1.5),
    DecodedNumber(kind="number", value=float("nan")),
    DecodedNumber(kind="number", value=float("inf")),
    DecodedNumber(kind="number", value=9007199254740992.0),
    DecodedString(kind="string", value="1.1"),
    DecodedString(kind="string", value="-1"),
])
def test_invalid_token_values_are_retained_as_invalid_not_zero(value: DecodedBoolean | DecodedInteger | DecodedNumber | DecodedString) -> None:
    normalized = _normalize("claude_code.api_request", (DecodedAttribute(key="input_tokens", value=value),))
    assert isinstance(normalized.activity, ModelRequest)
    assert isinstance(normalized.activity.usage.input, InvalidValue)


@pytest.mark.parametrize("count", [9007199254740993, 9223372036854775807])
def test_native_large_integers_preserve_every_digit(count: int) -> None:
    normalized = _normalize("claude_code.api_request", (_integer("input_tokens", count),))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.usage.input == ReportedInteger(kind="integer", value=count, representation="integer")
    assert NormalizedLogRecord.model_validate_json(normalized.model_dump_json()) == normalized


def test_derived_token_overflow_is_invalid_without_rejecting_reported_counters() -> None:
    normalized = _normalize("claude_code.api_request", (
        _integer("input_tokens", 9223372036854775807), _integer("cache_read_tokens", 1),
        _integer("cache_creation_tokens", 0), _integer("output_tokens", 1),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.usage.input == ReportedInteger(kind="integer", value=9223372036854775807, representation="integer")
    assert normalized.activity.usage.inclusive_input.kind == normalized.activity.usage.derived_total.kind == "invalid"


def test_cost_selection_and_comparison_ignore_ambient_decimal_precision() -> None:
    attributes = (_string("cost_usd", "12345678901234567890.123456789012345678"), _integer("cost_usd_micros", 123456789))
    expected = _normalize("claude_code.api_request", attributes)
    with localcontext() as context:
        context.prec = 2
        actual = _normalize("claude_code.api_request", attributes)
    assert actual == expected
    assert isinstance(actual.activity, ModelRequest)
    assert actual.activity.cost.agreement == "mismatch"
    assert actual.activity.cost.reported_usd == ReportedDecimal(kind="decimal", value="12345678901234567890.123456789012345678", representation="string")


@pytest.mark.parametrize("usd,micros", [
    ("9223372036854.775807", 9223372036854775807),
    ("0.000000000000000001", 1),
])
def test_cost_accounting_ignores_hostile_ambient_decimal_exponents_and_traps(usd: str, micros: int) -> None:
    attributes = (_string("cost_usd", usd), _integer("cost_usd_micros", micros))
    expected = _normalize("claude_code.api_request", attributes)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        for signal in context.traps:
            context.traps[signal] = True
        actual = _normalize("claude_code.api_request", attributes)
    assert actual == expected
    assert isinstance(actual.activity, ModelRequest)
    assert actual.activity.cost.selection == "micros"


def test_duplicate_keys_last_value_wins_before_capture_and_replay() -> None:
    normalized = _normalize("claude_code.api_request", (_integer("input_tokens", 99), _string("input_tokens", "0")))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.usage.input == ReportedInteger(kind="integer", value=0, representation="string")
    assert len([item for item in normalized.evidence.fields if item.key == "input_tokens"]) == 1


@pytest.mark.parametrize("usd,micros,selection,selected,agreement", [
    ("0.123456789", 123457, "micros", "0.123457", "within_micro_rounding"),
    ("0.123456", 123456, "micros", "0.123456", "exact"),
    ("0.1", 200000, "micros", "0.2", "mismatch"),
    ("0.000000000000000001", -1, "usd", "0.000000000000000001", "not_comparable"),
])
def test_claude_cost_alternatives_are_not_summed_and_rounding_is_not_corruption(usd: str, micros: int, selection: str, selected: str, agreement: str) -> None:
    normalized = _normalize("claude_code.api_request", (_string("cost_usd", usd), _integer("cost_usd_micros", micros)))
    assert isinstance(normalized.activity, ModelRequest)
    cost = normalized.activity.cost
    assert cost.selection == selection
    assert cost.selected_usd.kind == "decimal"
    assert cost.selected_usd.value == selected
    assert cost.agreement == agreement
    assert cost.reported_usd == ReportedDecimal(kind="decimal", value=usd, representation="string")
    assert cost.currency == "USD" and cost.authority == "producer_estimate" and cost.scope == "request"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "1e999", "1e-999", "9" * 97, "1e21"])
def test_pathological_or_negative_decimal_costs_are_invalid(value: str) -> None:
    normalized = _normalize("claude_code.api_request", (_string("cost_usd", value),))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.cost.reported_usd.kind == "invalid"
    assert normalized.activity.cost.selection == "unavailable"


def test_codex_completion_preserves_reported_total_and_does_not_add_cache_or_reasoning() -> None:
    normalized = _normalize("codex.sse_event", (
        _string("event.kind", "response.completed"), _string("model", "gpt-5"), _string("slug", "gpt-5.1"),
        _string("input_token_count", "1000"), _string("output_token_count", "200"),
        _integer("cached_token_count", 800), _integer("cache_write_token_count", 0),
        _integer("reasoning_token_count", 50), _string("tool_token_count", "1300"), _integer("ttft_ms", 15),
    ))
    assert isinstance(normalized.activity, ResponseUsage)
    usage = normalized.activity.usage
    assert usage.inclusive_input == ReportedInteger(kind="integer", value=1000, representation="string")
    assert usage.derived_total == ReportedInteger(kind="integer", value=1200, representation="integer")
    assert usage.reported_total == ReportedInteger(kind="integer", value=1300, representation="string")
    assert usage.reasoning_accounting == "included_in_output"
    assert usage.input_accounting == "includes_cache"
    assert normalized.activity.model != normalized.activity.slug
    assert normalized.activity.model_completion == "not_asserted"
    dimensions = {group.dimension for group in project_analytics_log(normalized).dimensions}
    assert LogDimension.ACTIVITY_KIND not in dimensions
    assert LogDimension.OUTCOME not in dimensions
    assert normalized.evidence.duration.kind == "missing"
    assert normalized.evidence.correlations == ()


@pytest.mark.parametrize("attributes,category", [
    ((_string("event.kind", "response.completed"),), "response.completed"),
    ((_string("event.kind", "private-event-secret"), _string("input_token_count", "20")), "unknown"),
    ((), "unknown"),
])
def test_completion_label_without_usage_and_arbitrary_stream_events_are_diagnostics(attributes: tuple[DecodedAttribute, ...], category: str) -> None:
    normalized = _normalize("codex.sse_event", attributes)
    assert isinstance(normalized.activity, StreamDiagnostic)
    assert normalized.activity.event_category == category
    assert "private-event-secret" not in normalized.model_dump_json()


def test_invalid_present_completion_usage_is_not_valid_success() -> None:
    normalized = _normalize("codex.sse_event", (
        _string("event.kind", "response.completed"),
        DecodedAttribute(key="input_token_count", value=DecodedInvalid(kind="invalid", reason="wrong_type")),
    ))
    assert isinstance(normalized.activity, ResponseUsage)
    assert normalized.activity.usage.input.kind == "invalid"
    assert normalized.activity.model_completion == "not_asserted"


def test_claude_terminal_error_never_claims_usage_or_cost_even_when_fields_are_present() -> None:
    normalized = _normalize("claude_code.api_error", (
        _integer("input_tokens", 100), _string("cost_usd", "0.1"), _integer("attempt", 3),
        _integer("status_code", 429), DecodedAttribute(key="error", value=DecodedBoolean(kind="boolean", value=True)),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.scope == "terminal_request"
    assert normalized.activity.transport_outcome == "failure"
    assert normalized.activity.usage.input.kind == "missing"
    assert normalized.activity.cost.selection == "unavailable"
    assert normalized.activity.attempt == ReportedInteger(kind="integer", value=3, representation="integer")


def test_codex_http_status_is_transport_only_and_request_identifiers_are_distinct() -> None:
    normalized = _normalize("codex.api_request", (
        _integer("attempt", 1), _integer("http.response.status_code", 200),
        DecodedAttribute(key="duration_ms", value=DecodedInteger(kind="integer", value=42)),
        DecodedAttribute(key="client_request_id", value=DecodedString(kind="string", value="client")),
        DecodedAttribute(key="auth.request_id", value=DecodedString(kind="string", value="auth")),
        _string("input_token_count", "100"),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.scope == "http_attempt"
    assert normalized.activity.transport_outcome == "success"
    assert normalized.activity.model_completion == "not_asserted"
    assert normalized.activity.usage.input.kind == "missing"
    assert normalized.activity.duration == ReportedDuration(kind="reported", value=42.0, unit="milliseconds")
    assert {item.key: item.value for item in normalized.evidence.correlations} == {
        "client_request_id": TextValue(kind="text", value="client"),
        "auth.request_id": TextValue(kind="text", value="auth"),
    }


@pytest.mark.parametrize("status,indicators,expected", [
    (302, (), "unknown"),
    (200, (DecodedAttribute(key="error.message", value=DecodedBoolean(kind="boolean", value=True)),), "failure"),
    (200, (DecodedAttribute(key="error.message", value=DecodedInvalid(kind="invalid", reason="wrong_type")),), "unknown"),
    (200, (DecodedAttribute(key="error.message", value=DecodedBoolean(kind="boolean", value=False)),), "success"),
])
def test_codex_http_outcome_requires_2xx_without_error_or_invalid_indicator(status: int, indicators: tuple[DecodedAttribute, ...], expected: str) -> None:
    normalized = _normalize("codex.api_request", (_integer("http.response.status_code", status), *indicators))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.transport_outcome == expected
    assert normalized.activity.model_completion == "not_asserted"


def test_websocket_explicit_success_remains_separate_from_error_indicator() -> None:
    normalized = _normalize("codex.websocket_request", (
        DecodedAttribute(key="success", value=DecodedString(kind="string", value="true")),
        DecodedAttribute(key="error.message", value=DecodedBoolean(kind="boolean", value=True)),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.transport_outcome == "success"
    assert normalized.activity.error_indicator.kind == "boolean"


def test_websocket_request_has_transport_outcome_without_usage_inference() -> None:
    normalized = _normalize("codex.websocket_request", (
        DecodedAttribute(key="success", value=DecodedString(kind="string", value="false")),
        DecodedAttribute(key="error.message", value=DecodedBoolean(kind="boolean", value=True)),
    ))
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.activity.scope == "websocket_request"
    assert normalized.activity.transport_outcome == "failure"
    assert normalized.activity.error_indicator.kind == "boolean"
    assert normalized.activity.usage.input.kind == "missing"


def test_turn_cost_retains_interruption_without_request_allocation() -> None:
    normalized = _normalize("codex.turn_cost", (
        _string("usage.estimated_usd", "0.000000123456789"),
        DecodedAttribute(key="turn.interrupted", value=DecodedBoolean(kind="boolean", value=True)),
        DecodedAttribute(key="turn.id", value=DecodedString(kind="string", value="turn-1")),
    ))
    assert isinstance(normalized.activity, TurnCost)
    assert normalized.activity.cost.scope == "turn"
    assert normalized.activity.cost.selected_usd == ReportedDecimal(kind="decimal", value="0.000000123456789", representation="string")
    assert normalized.activity.interrupted.kind == "boolean" and normalized.activity.interrupted.value is True
    assert normalized.evidence.correlations[0].key == "turn.id"


@pytest.mark.parametrize("service,event,expected", [
    ("other", "api_request", "unmapped"),
    ("codex_exec", "api_request", "model_request"),
    ("claude-code", "api_request", "model_request"),
    ("other", "claude_code.api_request", "model_request"),
    ("other", "codex.websocket_connect", "unmapped"),
])
def test_new_events_respect_qualification_and_source_gates(service: str, event: str, expected: str) -> None:
    normalized = normalize_log(
        _source(service, event, ""), TimestampEvidence(source_ns=1, observed_ns=0, receipt_ns=2, effective_source="source"),
        capture_producer_evidence(()),
    )
    assert normalized.activity.kind == expected


def test_semantic_request_takes_precedence_over_record_usage_and_retains_conflict() -> None:
    normalized = normalize_log(
        _source("codex", "codex.api_request", "codex.sse_event"),
        TimestampEvidence(source_ns=1, observed_ns=0, receipt_ns=2, effective_source="source"),
        capture_producer_evidence((_string("event.kind", "response.completed"), _string("input_token_count", "20"))),
    )
    assert isinstance(normalized.activity, ModelRequest)
    assert normalized.mapping.event_identity_conflict is True


@pytest.mark.parametrize("identifier", ["https://private.example/model", "person@example.org", "arn:aws:account:123", "folder/model", "folder\\model", "a" * 257])
def test_model_and_slug_reject_sensitive_structured_identifiers(identifier: str) -> None:
    normalized = _normalize("codex.sse_event", (
        _string("event.kind", "response.completed"), _string("input_token_count", "0"),
        _string("model", identifier), _string("slug", identifier), _string("error.message", "private-error-text"),
    ))
    assert isinstance(normalized.activity, ResponseUsage)
    assert normalized.activity.model.kind == normalized.activity.slug.kind == "invalid"
    serialized = normalized.model_dump_json()
    assert identifier not in serialized
    assert "private-error-text" not in serialized


def test_new_source_fields_reject_unapproved_payload_keys_and_canonical_unknown_fields() -> None:
    for key in ("query_source", "endpoint", "prompt", "body", "headers", "user.id", "skill.name", "service_tier", "model_reasoning_effort"):
        with pytest.raises(ValidationError):
            DecodedAttribute.model_validate({"key": key, "value": {"kind": "string", "value": "private"}})
    evidence = capture_producer_evidence(())
    with pytest.raises(ValidationError):
        ProducerEvidence.model_validate({**evidence.model_dump(), "unapproved": "private"})
    with pytest.raises(ValidationError):
        ProducerEvidence.model_validate({key: value for key, value in evidence.model_dump().items() if key != "fields"})


def test_frozen_v1_json_reads_and_replays_exact_old_shape_without_inventing_usage() -> None:
    path = Path(__file__).parents[4] / "support" / "normalized_log_v1.json"
    raw = path.read_text()
    restored = TypeAdapter(NormalizationEvidence).validate_json(raw)
    assert isinstance(restored, LegacyNormalizedLogRecord)
    assert restored.model_dump(mode="json") == json.loads(raw)
    replayed = normalize_log(restored.source, restored.timestamps, restored.evidence)
    assert replayed == restored
    assert replayed.model_dump(mode="json") == json.loads(raw)
    assert replayed.activity.kind == "unmapped"
    assert project_analytics_log(restored).normalization == restored
    upgraded = ProducerEvidence.model_validate({**restored.evidence.model_dump(), "schema_version": 2, "fields": ()})
    current = normalize_log(restored.source, restored.timestamps, upgraded)
    assert isinstance(current.activity, StreamDiagnostic)
    assert current.mapping.mapping_version == 2
