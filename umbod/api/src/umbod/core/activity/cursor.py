from base64 import b64decode, b64encode
from hashlib import sha256

from umbod.core.telemetry.analytics.write_models import OwnedLog
from umbod.core.usage.models import UsageWindowDays

from .models import ActivityPeriod, SessionCursor, SessionPosition


class InvalidSessionCursor(Exception):
    pass


def _binding(owner: OwnedLog) -> str:
    return sha256(f'umbod.activity.cursor.v1:{owner.owner_id}'.encode()).hexdigest()


def encode_session_cursor(
    owner: OwnedLog, period: ActivityPeriod, search: str, position: SessionPosition,
) -> str:
    cursor = SessionCursor(
        version=1, owner_binding=_binding(owner), days=period.days, as_of=period.as_of, search=search, position=position,
    )
    return b64encode(cursor.model_dump_json().encode(), altchars=b'-_').decode('ascii')


def decode_session_cursor(token: str, owner: OwnedLog, days: UsageWindowDays, search: str) -> SessionCursor:
    try:
        cursor = SessionCursor.model_validate_json(b64decode(token, altchars=b'-_', validate=True))
    except (ValueError, OverflowError):
        raise InvalidSessionCursor('Invalid session cursor') from None
    if (cursor.owner_binding, cursor.days, cursor.search) != (_binding(owner), days, search):
        raise InvalidSessionCursor('Session cursor does not match the current search')
    return cursor
