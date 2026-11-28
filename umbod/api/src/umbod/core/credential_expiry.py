from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    PlainSerializer,
    PlainValidator,
    TypeAdapter,
)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
_utc_datetime_adapter = TypeAdapter(UtcDatetime)


class NeverExpires(Enum):
    NEVER = "never"


def _parse_expiry(value: object) -> datetime | NeverExpires:
    if value is None or value is NeverExpires.NEVER:
        return NeverExpires.NEVER
    return _utc_datetime_adapter.validate_python(value)


def _serialize_expiry(expiry: datetime | NeverExpires) -> datetime | None:
    return expiry if isinstance(expiry, datetime) else None


CredentialExpiry = Annotated[
    UtcDatetime | NeverExpires,
    PlainValidator(_parse_expiry, json_schema_input_type=UtcDatetime | None),
    PlainSerializer(_serialize_expiry, when_used="json"),
]


def is_expired(expiry: CredentialExpiry, now: datetime) -> bool:
    return isinstance(expiry, datetime) and expiry <= now
