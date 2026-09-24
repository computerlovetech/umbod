import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return TestClient(create_app())


def test_connector_list_shows_unconfigured_status_and_no_publication_actions(
    client: TestClient,
) -> None:
    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert set(response.json()["connectors"][0]) == {
        "id",
        "display_name",
        "description",
        "extension",
        "publication_status",
        "available_actions",
    }
    assert response.json() == {
        "connectors": [
            {
                "id": "test",
                "display_name": "Test Connector",
                "description": "Provides a simple connector for validating configuration and MCP publishing flows",
                "extension": {"source": "built-in"},
                "publication_status": "unconfigured",
                "available_actions": ["configure"],
            }
        ]
    }


def test_capability_description_override_changes_emit_sanitized_durable_events(
    client: TestClient,
) -> None:
    set_response = client.put(
        "/admin/connector-capability-descriptions/native/test",
        json={
            "action": "set",
            "description": "Find deliberately renamed test capabilities",
            "expected_revision": 0,
        },
    )

    assert set_response.status_code == 200
    clear_response = client.put(
        "/admin/connector-capability-descriptions/native/test",
        json={"action": "clear", "expected_revision": 1},
    )
    assert clear_response.status_code == 200
    events_response = client.get(
        "/system/events",
        params={
            "after_sequence": 0,
            "limit": 100,
            "event_type": "connector.capability_description_override.changed",
        },
    )
    assert events_response.status_code == 200
    events = events_response.json()
    assert [event["event"]["metadata"] for event in events] == [
        {"connector_kind": "native", "connector_id": "test", "action": "set", "revision": "1"},
        {"connector_kind": "native", "connector_id": "test", "action": "clear", "revision": "2"},
    ]
    serialized_events = str(events)
    assert "Find deliberately" not in serialized_events
    assert "api_key" not in serialized_events
    assert "operation_name" not in serialized_events


def test_admin_saves_valid_configuration_as_draft_and_can_publish_it(client: TestClient) -> None:
    configuration_response = client.put(
        "/admin/connectors/catalog/test/configuration",
        json={
            "configuration": {
                "instance_name": "Demo",
                "api_key": "test-key",
                "default_response": "Hello from test connector",
            }
        },
    )

    list_response = client.get("/admin/connectors/catalog")
    publish_response = client.put("/admin/connectors/catalog/test/publication")
    published_list_response = client.get("/admin/connectors/catalog")
    system_events_response = client.get("/system/events?after_sequence=0&limit=100")
    publication_system_events_response = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.publication.changed"
    )
    configuration_system_events_response = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.configuration.changed"
    )

    assert configuration_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["connectors"][0]["publication_status"] == "draft"
    assert list_response.json()["connectors"][0]["available_actions"] == ["configure", "publish"]
    assert publish_response.status_code == 200
    assert publish_response.json() == {
        "connector_id": "test",
        "publication_status": "published",
    }
    assert published_list_response.json()["connectors"][0]["publication_status"] == "published"
    assert published_list_response.json()["connectors"][0]["available_actions"] == [
        "configure",
        "unpublish",
    ]
    assert system_events_response.status_code == 200
    assert [event["event"]["event_type"] for event in system_events_response.json()] == [
        "connector.configuration.changed",
        "connector.publication.changed",
    ]
    assert publication_system_events_response.status_code == 200
    assert publication_system_events_response.json()[0]["event"] == {
        "event_type": "connector.publication.changed",
        "subject": "connector:test",
        "metadata": {"connector_id": "test", "state": "published"},
        "occurred_at": publication_system_events_response.json()[0]["event"]["occurred_at"],
    }
    assert configuration_system_events_response.status_code == 200
    assert configuration_system_events_response.json()[0]["event"] == {
        "event_type": "connector.configuration.changed",
        "subject": "connector:test",
        "metadata": {"connector_id": "test"},
        "occurred_at": configuration_system_events_response.json()[0]["event"]["occurred_at"],
    }


def test_admin_unpublishes_connector_and_keeps_configuration_for_later_publishing(
    client: TestClient,
) -> None:
    client.put(
        "/admin/connectors/catalog/test/configuration",
        json={
            "configuration": {
                "instance_name": "Demo",
                "api_key": "test-key",
                "default_response": "Hello from test connector",
            }
        },
    )
    client.put("/admin/connectors/catalog/test/publication")

    unpublish_response = client.delete("/admin/connectors/catalog/test/publication")
    list_response = client.get("/admin/connectors/catalog")
    configuration_response = client.get("/admin/connectors/catalog/test/configuration")
    publication_events_response = client.get(
        "/system/events?after_sequence=2&limit=100&event_type=connector.publication.changed"
    )

    assert unpublish_response.status_code == 200
    assert unpublish_response.json() == {
        "connector_id": "test",
        "publication_status": "unpublished",
    }
    assert list_response.json()["connectors"][0]["publication_status"] == "unpublished"
    assert list_response.json()["connectors"][0]["available_actions"] == ["configure", "publish"]
    assert configuration_response.json()["configuration"] == {
        "instance_name": "Demo",
        "api_key": "**********",
        "default_response": "Hello from test connector",
    }
    assert publication_events_response.status_code == 200
    assert publication_events_response.json()[0]["event"] == {
        "event_type": "connector.publication.changed",
        "subject": "connector:test",
        "metadata": {"connector_id": "test", "state": "unpublished"},
        "occurred_at": publication_events_response.json()[0]["event"]["occurred_at"],
    }


def test_publish_is_blocked_when_saved_configuration_fails_connector_check(
    client: TestClient,
) -> None:
    client.put(
        "/admin/connectors/catalog/test/configuration",
        json={
            "configuration": {
                "instance_name": "Demo",
                "api_key": "invalid-key",
                "default_response": "Hello",
            }
        },
    )

    publish_response = client.put("/admin/connectors/catalog/test/publication")
    list_response = client.get("/admin/connectors/catalog")

    assert publish_response.status_code == 422
    assert publish_response.json() == {
        "valid": False,
        "message": 'Test Connector API key must be "test-key" before publishing.',
        "field_messages": {"api_key": 'Use "test-key" for the local Test Connector.'},
    }
    assert list_response.json()["connectors"][0]["publication_status"] == "draft"
