from umbod.core.publishing.events import ConnectorPublicationChanged, ConnectorPublicationStreamEvent
from umbod.core.configuration.events import ConnectorRuntimeStateChanged, ConnectorRuntimeStateStreamEvent
from messaging.models import StreamEvent


def test_connector_publication_changed_converts_to_and_from_messaging_event() -> None:
    event = ConnectorPublicationChanged(connector_id="slack", state="published")

    messaging_event = event.to_messaging_event()
    stream_event = ConnectorPublicationStreamEvent.from_stream_event(
        StreamEvent(sequence=7, event=messaging_event)
    )

    assert messaging_event.event_type == "connector.publication.changed"
    assert messaging_event.subject == "connector:slack"
    assert messaging_event.metadata == {"connector_id": "slack", "state": "published"}
    assert stream_event.sequence == 7
    assert stream_event.event == event


def test_connector_runtime_state_changed_converts_to_and_from_messaging_event() -> None:
    event = ConnectorRuntimeStateChanged(connector_id="slack")

    messaging_event = event.to_messaging_event()
    stream_event = ConnectorRuntimeStateStreamEvent.from_stream_event(
        StreamEvent(sequence=8, event=messaging_event)
    )

    assert messaging_event.event_type == "connector.configuration.changed"
    assert messaging_event.subject == "connector:slack"
    assert messaging_event.metadata == {"connector_id": "slack"}
    assert stream_event.sequence == 8
    assert stream_event.event == event
