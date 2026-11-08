from typing import Literal

from .accounting import field, integer, producer_cost, token_usage
from .models import (
    ExtendedActivity, InvalidValue, MissingValue, ModelRequest, Outcome, ProducerEvidence,
    ReportedBoolean, ReportedInteger, ResponseUsage, StreamDiagnostic, TextEvidence,
    TextValue, TurnCost, UnmappedActivity,
)


CODEX_USAGE_KEYS = frozenset(("input_token_count", "output_token_count", "cached_token_count", "cache_write_token_count", "reasoning_token_count", "tool_token_count"))


def _text(evidence: ProducerEvidence, key: str) -> TextEvidence:
    value = field(evidence, key)
    return value if isinstance(value, (MissingValue, InvalidValue, TextValue)) else InvalidValue(kind="invalid", reason="wrong_type")


def _boolean(evidence: ProducerEvidence, key: str) -> MissingValue | InvalidValue | ReportedBoolean:
    value = field(evidence, key)
    return value if isinstance(value, (MissingValue, InvalidValue, ReportedBoolean)) else InvalidValue(kind="invalid", reason="wrong_type")


def _request(evidence: ProducerEvidence, producer: Literal["claude", "codex"], event: str) -> ModelRequest:
    websocket = event == "websocket_request"
    terminal_error = producer == "claude" and event == "api_error"
    claude_usage = producer == "claude" and not terminal_error
    status = integer(evidence, "status_code" if producer == "claude" else "http.response.status_code")
    error_indicator = _boolean(evidence, "error" if producer == "claude" else "error.message")
    transport: Outcome = "unknown"
    if websocket:
        transport = "success" if evidence.success.state == "true" else "failure" if evidence.success.state == "false" else "unknown"
    elif isinstance(error_indicator, ReportedBoolean) and error_indicator.value:
        transport = "failure"
    elif isinstance(status, ReportedInteger) and 100 <= status.value <= 599:
        transport = "failure" if status.value >= 400 else "success" if 200 <= status.value < 300 and not isinstance(error_indicator, InvalidValue) else "unknown"
    if terminal_error:
        transport = "failure"
    return ModelRequest(
        kind="model_request", scope="terminal_request" if producer == "claude" else "websocket_request" if websocket else "http_attempt",
        model=_text(evidence, "model"), duration=evidence.duration, attempt=integer(evidence, "attempt"),
        status_code=status, transport_outcome=transport, model_completion="not_asserted",
        error_indicator=error_indicator,
        usage=token_usage(evidence, "claude" if claude_usage else "none"),
        cost=producer_cost(evidence, "request", claude_usage),
    )


def request_activity(source: str, event: str, evidence: ProducerEvidence) -> ExtendedActivity:
    if event.startswith("claude_code."):
        producer, name = "claude", event.removeprefix("claude_code.")
    elif event.startswith("codex."):
        producer, name = "codex", event.removeprefix("codex.")
    elif source in ("claude-code", "claude-code-desktop"):
        producer, name = "claude", event
    elif source in ("codex", "codex_exec"):
        producer, name = "codex", event
    else:
        return UnmappedActivity(kind="unmapped")
    if producer == "claude" and name in ("api_request", "api_error"):
        return _request(evidence, "claude", name)
    if producer == "codex" and name in ("api_request", "websocket_request"):
        return _request(evidence, "codex", name)
    if producer == "codex" and name == "turn_cost":
        return TurnCost(kind="turn_cost", cost=producer_cost(evidence, "turn", True), interrupted=_boolean(evidence, "turn.interrupted"))
    if producer == "codex" and name == "sse_event":
        category = _text(evidence, "event.kind")
        completed = isinstance(category, TextValue) and category.value == "response.completed"
        if completed and any(item.key in CODEX_USAGE_KEYS for item in evidence.fields):
            return ResponseUsage(
                kind="response_usage", model=_text(evidence, "model"), slug=_text(evidence, "slug"),
                usage=token_usage(evidence, "codex"), ttft_ms=integer(evidence, "ttft_ms"), model_completion="not_asserted",
            )
        return StreamDiagnostic(kind="stream_diagnostic", event_category="response.completed" if completed else "unknown", model_completion="not_asserted")
    return UnmappedActivity(kind="unmapped")
