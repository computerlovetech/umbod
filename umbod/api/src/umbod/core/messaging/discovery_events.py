from messaging.models import MessagingEvent


def connector_discovery_changed_event(connector_kind: str, connector_id: str) -> MessagingEvent:
    return MessagingEvent(
        event_type="connector.discovery.changed",
        subject=f"connector:{connector_id}",
        metadata={"connector_kind": connector_kind, "connector_id": connector_id},
    )
