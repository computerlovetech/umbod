from typing import Literal

from messaging.models import MessagingEvent


def connector_publication_changed_event(
    connector_id: str, state: Literal["published", "unpublished"]
) -> MessagingEvent:
    return MessagingEvent(
        event_type="connector.publication.changed",
        subject=f"connector:{connector_id}",
        metadata={"connector_id": connector_id, "state": state},
    )


__all__ = ["connector_publication_changed_event"]
