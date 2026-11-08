from decimal import Decimal, InvalidOperation
from re import fullmatch
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


def is_approved_schema_url(value: str) -> bool:
    return fullmatch(r"https://opentelemetry\.io/schemas/[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", value) is not None


def decimal_value(value: str) -> Decimal:
    if len(value) > 96 or fullmatch(r"[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?", value) is None:
        raise ValueError("Invalid decimal representation")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid decimal representation") from error
    if not number.is_finite() or number < 0 or number > Decimal("1e20") or number.as_tuple().exponent < -18:
        raise ValueError("Decimal outside bounds")
    return number


class NormalizationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MissingValue(NormalizationModel):
    kind: Literal["missing"]


class InvalidValue(NormalizationModel):
    kind: Literal["invalid"]
    reason: Literal["wrong_type", "oversize", "unrecognized", "out_of_range"]


class TextValue(NormalizationModel):
    kind: Literal["text"]
    value: str


TextEvidence = Annotated[MissingValue | InvalidValue | TextValue, Field(discriminator="kind")]


class ScalarEvidence(NormalizationModel):
    state: Literal["missing", "invalid", "true", "false", "success", "failure", "unknown"]
    representation: Literal["missing", "invalid", "boolean", "string"]
    reason: Literal["missing", "valid", "wrong_type", "oversize", "unrecognized"]


class TimestampEvidence(NormalizationModel):
    source_ns: Annotated[int, Field(ge=0)]
    observed_ns: Annotated[int, Field(ge=0)]
    receipt_ns: int
    effective_source: Literal["source", "observed", "receipt"]


class SourceEvidence(NormalizationModel):
    service: TextEvidence
    service_version: TextEvidence
    app_version: TextEvidence
    scope_name: TextEvidence
    scope_version: TextEvidence
    resource_schema_url: TextEvidence
    scope_schema_url: TextEvidence
    record_event: TextEvidence
    semantic_event: TextEvidence
    severity_text: TextEvidence
    severity_number: Annotated[int, Field(ge=0, le=24)] | InvalidValue

    @model_validator(mode="after")
    def safe_metadata(self) -> Self:
        for value in (self.service_version, self.app_version, self.scope_name, self.scope_version):
            if isinstance(value, TextValue) and len(value.value) > 1024:
                raise ValueError("Source metadata exceeds normalization bounds")
        for value in (self.resource_schema_url, self.scope_schema_url):
            if isinstance(value, TextValue) and not is_approved_schema_url(value.value):
                raise ValueError("Source schema URL is not approved")
        return self


CorrelationKey = Literal[
    "session.id", "session_id", "conversation.id", "conversation_id", "mcp.session.id",
    "turn.id", "turn_id", "prompt.id", "prompt_id", "request.id", "request_id",
    "tool_call.id", "tool_call_id", "call_id", "tool_use_id", "trace_id", "span_id",
    "client_request_id", "auth.request_id",
]


class CorrelationEvidence(NormalizationModel):
    key: CorrelationKey
    value: TextEvidence


class ToolAlias(NormalizationModel):
    key: Literal["tool.name", "tool_name", "mcp.tool.name"]
    value: TextEvidence


class ToolProvenance(NormalizationModel):
    origin: Literal["external", "native", "unknown"]
    basis: Literal["explicit", "assumed", "unknown"]
    namespace: Literal["mcp", "custom", "native", "functions", "unknown", "missing"]
    external_indicator: bool


class MappingFields(NormalizationModel):
    producer: Literal["codex", "claude", "generic"]
    mapping_id: Literal["umbod.activity", "codex.events", "claude.events", "unmapped"]
    recognition: Literal["declared", "qualified_event", "source_gated_event", "unmapped"]
    authority: Literal["producer_claim"]
    service_conflict: bool
    declaration_event_conflict: bool
    event_identity_conflict: bool


class MissingDuration(NormalizationModel):
    kind: Literal["missing"]


class InvalidDuration(NormalizationModel):
    kind: Literal["invalid"]
    reason: Literal["wrong_type", "out_of_range", "unrecognized", "oversize"]


class ReportedDuration(NormalizationModel):
    kind: Literal["reported"]
    value: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    unit: Literal["milliseconds", "seconds", "nanoseconds"]


DurationEvidence = Annotated[MissingDuration | InvalidDuration | ReportedDuration, Field(discriminator="kind")]
ActivityKind = Literal["tool_call", "file_read", "file_edit"]
Outcome = Literal["success", "failure", "unknown"]


class ToolActivity(NormalizationModel):
    kind: Literal["tool_result"]
    activity_kind: ActivityKind
    outcome: Outcome
    tool_name: TextEvidence
    provenance: ToolProvenance
    duration: DurationEvidence
    completion: Literal["reported_wrapper_result", "declared_activity"]


class PermissionDecision(NormalizationModel):
    kind: Literal["permission_decision"]
    decision: Literal["accept", "reject", "unknown"]
    execution: Literal["not_asserted"]


class SkillActivation(NormalizationModel):
    kind: Literal["skill_activation"]
    trigger: Literal["explicit", "implicit", "nested", "unknown"]


class UnmappedActivity(NormalizationModel):
    kind: Literal["unmapped"]


Activity = Annotated[ToolActivity | PermissionDecision | SkillActivation | UnmappedActivity, Field(discriminator="kind")]


class ProducerFields(NormalizationModel):
    declared_kind: TextEvidence
    declared_outcome: ScalarEvidence
    success: ScalarEvidence
    tool_aliases: tuple[ToolAlias, ...]
    tool_provenance: ToolProvenance
    correlations: tuple[CorrelationEvidence, ...]
    duration: DurationEvidence
    decision: Literal[
        "accept", "reject", "unknown", "approved", "approved_with_amendment",
        "approved_for_session", "approved_mcp_policy_amendment",
        "approved_with_network_policy_allow", "denied_with_network_policy_deny",
        "denied", "timed_out", "abort",
    ]
    skill_trigger: Literal["explicit", "implicit", "user-slash", "claude-proactive", "nested-skill", "unknown"]
    skill_invocation_type: Literal["explicit", "implicit", "unknown"]


class LegacyMappingEvidence(MappingFields):
    mapping_version: Literal[1]


class MappingEvidence(MappingFields):
    mapping_version: Literal[2]


class LegacyProducerEvidence(ProducerFields):
    schema_version: Literal[1]


class ReportedInteger(NormalizationModel):
    kind: Literal["integer"]
    value: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]
    representation: Literal["integer", "double", "string"]

    @model_validator(mode="after")
    def safe_double(self) -> Self:
        if self.representation == "double" and self.value > 9007199254740991:
            raise ValueError("Double integer exceeds exact bounds")
        return self


class ReportedDecimal(NormalizationModel):
    kind: Literal["decimal"]
    value: str
    representation: Literal["integer", "double", "string"]

    @model_validator(mode="after")
    def bounded_decimal(self) -> Self:
        decimal_value(self.value)
        return self


class ReportedBoolean(NormalizationModel):
    kind: Literal["boolean"]
    value: bool


IntegerEvidence = Annotated[MissingValue | InvalidValue | ReportedInteger, Field(discriminator="kind")]
DecimalEvidence = Annotated[MissingValue | InvalidValue | ReportedDecimal, Field(discriminator="kind")]
ProducerValue = Annotated[MissingValue | InvalidValue | ReportedInteger | ReportedDecimal | ReportedBoolean | TextValue, Field(discriminator="kind")]
ProducerFieldKey = Literal[
    "model", "slug", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
    "cache_creation_5m_tokens", "cache_creation_1h_tokens", "cost_usd", "cost_usd_micros",
    "speed", "effort", "attempt", "status_code", "http.response.status_code", "error", "error.message",
    "event.kind", "input_token_count", "output_token_count", "cached_token_count",
    "cache_write_token_count", "reasoning_token_count", "tool_token_count", "ttft_ms",
    "usage.estimated_usd", "turn.interrupted",
]


class ProducerField(NormalizationModel):
    key: ProducerFieldKey
    value: ProducerValue

    @model_validator(mode="after")
    def safe_text(self) -> Self:
        if isinstance(self.value, TextValue):
            categories = {"speed": ("fast", "normal"), "effort": ("low", "medium", "high", "xhigh", "max"), "event.kind": ("response.completed",)}
            if self.key in ("model", "slug"):
                if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}", self.value.value) is None:
                    raise ValueError("Invalid producer identifier")
            elif self.value.value not in categories.get(self.key, ()):
                raise ValueError("Unapproved producer text")
        return self


class ProducerEvidence(ProducerFields):
    schema_version: Literal[2]
    fields: tuple[ProducerField, ...]


class TokenUsage(NormalizationModel):
    input: IntegerEvidence
    output: IntegerEvidence
    cache_read: IntegerEvidence
    cache_creation: IntegerEvidence
    cache_creation_5m: IntegerEvidence
    cache_creation_1h: IntegerEvidence
    reasoning: IntegerEvidence
    reported_total: IntegerEvidence
    inclusive_input: IntegerEvidence
    derived_total: IntegerEvidence
    input_accounting: Literal["excludes_cache", "includes_cache", "not_reported"]
    reasoning_accounting: Literal["included_in_output", "not_reported"]
    zero_authority: Literal["producer_report_only"]


class ProducerCost(NormalizationModel):
    currency: Literal["USD"]
    authority: Literal["producer_estimate"]
    scope: Literal["request", "turn"]
    reported_usd: DecimalEvidence
    reported_micros: IntegerEvidence
    selected_usd: DecimalEvidence
    selection: Literal["micros", "usd", "unavailable"]
    agreement: Literal["exact", "within_micro_rounding", "mismatch", "not_comparable"]


class ModelRequest(NormalizationModel):
    kind: Literal["model_request"]
    scope: Literal["http_attempt", "terminal_request", "websocket_request"]
    model: TextEvidence
    duration: DurationEvidence
    attempt: IntegerEvidence
    status_code: IntegerEvidence
    transport_outcome: Outcome
    model_completion: Literal["not_asserted"]
    error_indicator: Annotated[MissingValue | InvalidValue | ReportedBoolean, Field(discriminator="kind")]
    usage: TokenUsage
    cost: ProducerCost


class ResponseUsage(NormalizationModel):
    kind: Literal["response_usage"]
    model: TextEvidence
    slug: TextEvidence
    usage: TokenUsage
    ttft_ms: IntegerEvidence
    model_completion: Literal["not_asserted"]


class StreamDiagnostic(NormalizationModel):
    kind: Literal["stream_diagnostic"]
    event_category: Literal["response.completed", "unknown"]
    model_completion: Literal["not_asserted"]


class TurnCost(NormalizationModel):
    kind: Literal["turn_cost"]
    cost: ProducerCost
    interrupted: Annotated[MissingValue | InvalidValue | ReportedBoolean, Field(discriminator="kind")]


ExtendedActivity = Annotated[ToolActivity | PermissionDecision | SkillActivation | UnmappedActivity | ModelRequest | ResponseUsage | StreamDiagnostic | TurnCost, Field(discriminator="kind")]


class LegacyNormalizedLogRecord(NormalizationModel):
    kind: Literal["normalized"]
    schema_version: Literal[1]
    source: SourceEvidence
    timestamps: TimestampEvidence
    evidence: LegacyProducerEvidence
    mapping: LegacyMappingEvidence
    selected_event: TextEvidence
    activity: Activity


class NormalizedLogRecord(NormalizationModel):
    kind: Literal["normalized"]
    schema_version: Literal[2]
    source: SourceEvidence
    timestamps: TimestampEvidence
    evidence: ProducerEvidence
    mapping: MappingEvidence
    selected_event: TextEvidence
    activity: ExtendedActivity


class UnavailableLogNormalization(NormalizationModel):
    kind: Literal["unavailable"]
    reason: Literal["legacy_or_unspecified"]


NormalizedRecord = Annotated[LegacyNormalizedLogRecord | NormalizedLogRecord, Field(discriminator="schema_version")]
NormalizationEvidence = Annotated[NormalizedRecord | UnavailableLogNormalization, Field(discriminator="kind")]
