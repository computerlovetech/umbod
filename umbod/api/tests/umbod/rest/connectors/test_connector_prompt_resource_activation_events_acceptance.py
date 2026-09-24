import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from tests.support.connector_plugins import TestConnectorPlugin


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    registration = TestConnectorPlugin.registration()
    registration["prompt_descriptions"] = [
        {
            "name": "summarize",
            "description": "Summarize an article.",
            "arguments": [
                {"name": "article_id", "description": "Article identifier.", "required": True}
            ],
        }
    ]
    registration["resource_descriptions"] = [
        {
            "kind": "resource",
            "name": "Guide",
            "description": "Knowledge guide.",
            "uri": "kb://guide",
        },
        {
            "kind": "resource_template",
            "name": "Article",
            "description": "Knowledge article.",
            "uri": "kb://articles/{article_id}",
        },
    ]
    return TestClient(create_app(connector_registrations=[registration]))


def test_prompt_activation_put_emits_capability_activation_changed_event(client: TestClient) -> None:
    response = client.put(
        "/admin/connectors/catalog/test/prompts/activation",
        json={"prompts": [{"prompt_id": "summarize", "activation_status": "enabled"}]},
    )
    events = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.capability_activation.changed"
    ).json()

    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "test",
        "prompts": [{"prompt_id": "summarize", "activation_status": "enabled"}],
    }
    assert events[-1]["event"]["metadata"] == {
        "connector_kind": "native",
        "connector_id": "test",
        "capability_kind": "prompt",
        "capability_key": "summarize",
    }


def test_resource_activation_put_emits_capability_activation_changed_events(
    client: TestClient,
) -> None:
    response = client.put(
        "/admin/connectors/catalog/test/resources/activation",
        json={
            "resources": [
                {
                    "resource_id": "kb://guide",
                    "kind": "resource",
                    "activation_status": "enabled",
                },
                {
                    "resource_id": "kb://articles/{article_id}",
                    "kind": "resource_template",
                    "activation_status": "enabled",
                },
            ]
        },
    )
    events = client.get(
        "/system/events?after_sequence=0&limit=100&event_type=connector.capability_activation.changed"
    ).json()

    assert response.status_code == 200
    assert {event["event"]["metadata"]["capability_kind"] for event in events[-2:]} == {
        "resource",
        "resource_template",
    }
    assert {event["event"]["metadata"]["capability_key"] for event in events[-2:]} == {
        "kb://guide",
        "kb://articles/{article_id}",
    }
