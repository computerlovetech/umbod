from messaging.models import MessagingEvent
from umbod.core.messaging.stores.event_stream import append_event_in_session
from umbod.core.persistence import DatabaseSession

from ..authorization.discovery import FILESYSTEM_DISCOVERY_CHANGED


async def append_discovery_changed(session: DatabaseSession) -> None:
    await append_event_in_session(
        session,
        MessagingEvent(
            event_type=FILESYSTEM_DISCOVERY_CHANGED,
            subject="filesystem",
            metadata={},
        ),
    )
