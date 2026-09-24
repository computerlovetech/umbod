import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model

from umbod.rest.main import create_app


class SlackAdminConfiguration(Model):
    model_config = ConfigDict(extra="forbid")

    workspace_name: str
    bot_token: SecretStr
    default_channel_id: str


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "slack"}]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return TestClient(
        create_app(
            connector_registrations=[
                {
                    "id": "slack",
                    "display_name": "Slack",
                    "capability_description": "Search and manage Slack conversations",
                    "description": "Connects to Slack",
                    "extension": {"source": "built-in"},
                    "configuration_schema": SlackAdminConfiguration,
                },
                {
                    "id": "github",
                    "display_name": "GitHub",
                    "capability_description": "Search and manage GitHub resources",
                    "description": "Connects to GitHub",
                    "extension": {"source": "built-in"},
                    "configuration_schema": SlackAdminConfiguration,
                },
            ]
        )
    )


def test_system_runtime_state_list_returns_raw_configuration_publication_and_availability(
    client: TestClient,
) -> None:
    client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-secret",
                "default_channel_id": "C123",
            }
        },
    )
    client.put("/admin/connectors/catalog/slack/publication")

    response = client.get("/system/connectors/runtime-state")

    assert response.status_code == 200
    states = {state["connector_id"]: state for state in response.json()}
    assert states["slack"] == {
        "connector_id": "slack",
        "display_name": "Slack",
        "available": True,
        "published": True,
        "configuration": {
            "workspace_name": "Acme",
            "bot_token": "xoxb-secret",
            "default_channel_id": "C123",
        },
    }
    assert states["github"] == {
        "connector_id": "github",
        "display_name": "GitHub",
        "available": False,
        "published": False,
        "configuration": None,
    }


def test_system_runtime_state_single_returns_raw_source_of_truth_state(client: TestClient) -> None:
    client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-secret",
                "default_channel_id": "C123",
            }
        },
    )

    response = client.get("/system/connectors/slack/runtime-state")

    assert response.status_code == 200
    assert response.json()["configuration"]["bot_token"] == "xoxb-secret"
    assert response.json()["available"] is True
    assert response.json()["published"] is False


def test_system_runtime_state_single_returns_404_for_unknown_connector(client: TestClient) -> None:
    response = client.get("/system/connectors/unknown/runtime-state")

    assert response.status_code == 404
