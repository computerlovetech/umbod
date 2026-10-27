from umbod.core.activation.events import connector_capability_activation_changed_event
from umbod.core.configuration.events import connector_configuration_changed_event
from umbod.core.publishing.events import connector_publication_changed_event


def test_connector_publication_event_contains_only_change_metadata() -> None:
    event = connector_publication_changed_event("slack", "published")
    assert event.event_type == "connector.publication.changed"
    assert event.subject == "connector:slack"
    assert event.metadata == {"connector_id": "slack", "state": "published"}


def test_connector_configuration_event_contains_only_identity() -> None:
    event = connector_configuration_changed_event("slack")
    assert event.event_type == "connector.configuration.changed"
    assert event.subject == "connector:slack"
    assert event.metadata == {"connector_id": "slack"}


def test_capability_activation_event_does_not_capture_authorization_state() -> None:
    event = connector_capability_activation_changed_event("native", "slack", "tool", "read")
    assert event.event_type == "connector.capability_activation.changed"
    assert event.metadata == {
        "connector_kind": "native",
        "connector_id": "slack",
        "capability_kind": "tool",
        "capability_key": "read",
    }
