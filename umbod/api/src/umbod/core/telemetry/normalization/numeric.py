from math import isfinite
from re import fullmatch
from typing import get_args

from .decoding import DecodedBoolean, DecodedInteger, DecodedInvalid, DecodedNumber, DecodedString, DecodedValue
from .models import (
    DecimalEvidence, IntegerEvidence, InvalidValue, ProducerField,
    ProducerFieldKey, ProducerValue, ReportedBoolean, ReportedDecimal, ReportedInteger, TextValue, decimal_value,
)


DECIMAL_KEYS = frozenset(("cost_usd", "usage.estimated_usd"))
TEXT_CATEGORIES = {
    "speed": ("fast", "normal"),
    "effort": ("low", "medium", "high", "xhigh", "max"),
    "event.kind": ("response.completed",),
}
BOOLEAN_KEYS = frozenset(("error", "error.message", "turn.interrupted"))
IDENTIFIER_KEYS = frozenset(("model", "slug"))


def capture_integer(value: DecodedValue) -> IntegerEvidence:
    representation = "integer" if isinstance(value, DecodedInteger) else "double" if isinstance(value, DecodedNumber) else "string"
    if not isinstance(value, (DecodedInteger, DecodedNumber, DecodedString)):
        return InvalidValue(kind="invalid", reason=value.reason if isinstance(value, DecodedInvalid) else "wrong_type")
    if isinstance(value, DecodedNumber) and (not isfinite(value.value) or abs(value.value) > 9007199254740991):
        return InvalidValue(kind="invalid", reason="out_of_range")
    try:
        number = decimal_value(str(value.value))
    except ValueError:
        return InvalidValue(kind="invalid", reason="out_of_range")
    if number != number.to_integral_value() or number > 9223372036854775807:
        return InvalidValue(kind="invalid", reason="out_of_range")
    return ReportedInteger.model_validate({"kind": "integer", "value": int(number), "representation": representation})


def capture_decimal(value: DecodedValue) -> DecimalEvidence:
    if not isinstance(value, (DecodedInteger, DecodedNumber, DecodedString)):
        return InvalidValue(kind="invalid", reason=value.reason if isinstance(value, DecodedInvalid) else "wrong_type")
    raw = str(value.value)
    try:
        decimal_value(raw)
    except ValueError:
        return InvalidValue(kind="invalid", reason="out_of_range")
    representation = "integer" if isinstance(value, DecodedInteger) else "double" if isinstance(value, DecodedNumber) else "string"
    return ReportedDecimal.model_validate({"kind": "decimal", "value": raw, "representation": representation})


def _capture_field(key: str, value: DecodedValue) -> ProducerValue:
    if key in DECIMAL_KEYS:
        return capture_decimal(value)
    if key in BOOLEAN_KEYS:
        return ReportedBoolean(kind="boolean", value=value.value) if isinstance(value, DecodedBoolean) else InvalidValue(kind="invalid", reason="wrong_type")
    if key in IDENTIFIER_KEYS or key in TEXT_CATEGORIES:
        if not isinstance(value, DecodedString):
            return InvalidValue(kind="invalid", reason=value.reason if isinstance(value, DecodedInvalid) else "wrong_type")
        allowed = fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}", value.value) is not None if key in IDENTIFIER_KEYS else value.value in TEXT_CATEGORIES[key]
        return TextValue(kind="text", value=value.value) if allowed else InvalidValue(kind="invalid", reason="unrecognized")
    return capture_integer(value)


def capture_fields(attributes: dict[str, DecodedValue]) -> tuple[ProducerField, ...]:
    return tuple(ProducerField.model_validate({"key": key, "value": _capture_field(key, attributes[key])}) for key in get_args(ProducerFieldKey) if key in attributes)
