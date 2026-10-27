from messaging.models import MessagingEvent


def connector_configuration_changed_event(connector_id: str) -> MessagingEvent:
    return MessagingEvent(
        event_type="connector.configuration.changed",
        subject=f"connector:{connector_id}",
        metadata={"connector_id": connector_id},
    )


__all__ = ["connector_configuration_changed_event"]
