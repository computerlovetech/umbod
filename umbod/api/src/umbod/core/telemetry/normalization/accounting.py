from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
from typing import Literal

from .models import (
    DecimalEvidence, IntegerEvidence, InvalidValue, MissingValue, ProducerCost,
    ProducerEvidence, ProducerValue, ReportedDecimal, ReportedInteger, TokenUsage,
)
from .numeric import decimal_value


def field(evidence: ProducerEvidence, key: str) -> ProducerValue:
    return next((item.value for item in evidence.fields if item.key == key), MissingValue(kind="missing"))


def integer(evidence: ProducerEvidence, key: str) -> IntegerEvidence:
    value = field(evidence, key)
    return value if isinstance(value, (MissingValue, InvalidValue, ReportedInteger)) else InvalidValue(kind="invalid", reason="wrong_type")


def decimal(evidence: ProducerEvidence, key: str) -> DecimalEvidence:
    value = field(evidence, key)
    return value if isinstance(value, (MissingValue, InvalidValue, ReportedDecimal)) else InvalidValue(kind="invalid", reason="wrong_type")


def _sum(values: tuple[IntegerEvidence, ...]) -> IntegerEvidence:
    if any(isinstance(value, InvalidValue) for value in values):
        return InvalidValue(kind="invalid", reason="out_of_range")
    if not all(isinstance(value, ReportedInteger) for value in values):
        return MissingValue(kind="missing")
    total = sum(value.value for value in values if isinstance(value, ReportedInteger))
    if total > 9223372036854775807:
        return InvalidValue(kind="invalid", reason="out_of_range")
    return ReportedInteger(kind="integer", value=total, representation="integer")


def token_usage(evidence: ProducerEvidence, producer: Literal["claude", "codex", "none"]) -> TokenUsage:
    keys = {
        "claude": ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "cache_creation_5m_tokens", "cache_creation_1h_tokens", "", ""),
        "codex": ("input_token_count", "output_token_count", "cached_token_count", "cache_write_token_count", "", "", "reasoning_token_count", "tool_token_count"),
        "none": ("", "", "", "", "", "", "", ""),
    }[producer]
    input_count, output, read, creation, five, hour, reasoning, total = (integer(evidence, key) for key in keys)
    inclusive = _sum((input_count, read, creation)) if producer == "claude" else input_count
    return TokenUsage(
        input=input_count, output=output, cache_read=read, cache_creation=creation,
        cache_creation_5m=five, cache_creation_1h=hour, reasoning=reasoning,
        reported_total=total, inclusive_input=inclusive, derived_total=_sum((inclusive, output)),
        input_accounting="excludes_cache" if producer == "claude" else "includes_cache" if producer == "codex" else "not_reported",
        reasoning_accounting="included_in_output" if producer == "codex" else "not_reported",
        zero_authority="producer_report_only",
    )


def producer_cost(evidence: ProducerEvidence, scope: Literal["request", "turn"], enabled: bool) -> ProducerCost:
    usd = decimal(evidence, "cost_usd" if scope == "request" else "usage.estimated_usd") if enabled else MissingValue(kind="missing")
    micros = integer(evidence, "cost_usd_micros") if enabled and scope == "request" else MissingValue(kind="missing")
    selected: DecimalEvidence = usd
    selection: Literal["micros", "usd", "unavailable"] = "usd" if isinstance(usd, ReportedDecimal) else "unavailable"
    agreement: Literal["exact", "within_micro_rounding", "mismatch", "not_comparable"] = "not_comparable"
    if isinstance(micros, ReportedInteger):
        with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN, Emin=-128, Emax=128, traps=[InvalidOperation, DivisionByZero, Overflow])):
            micro_usd = Decimal(micros.value) / Decimal(1000000)
            selected = ReportedDecimal(kind="decimal", value=format(micro_usd, "f"), representation=micros.representation)
            selection = "micros"
            if isinstance(usd, ReportedDecimal):
                difference = abs(decimal_value(usd.value) - micro_usd)
                agreement = "exact" if difference == 0 else "within_micro_rounding" if difference <= Decimal("0.000001") else "mismatch"
    return ProducerCost(
        currency="USD", authority="producer_estimate", scope=scope,
        reported_usd=usd, reported_micros=micros, selected_usd=selected,
        selection=selection, agreement=agreement,
    )
