import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from tests.support.connector_plugins import SlackConnectorPlugin, TestConnectorPlugin


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return TestClient(create_app())


def test_api_consumer_views_available_connector_with_agent_facing_tools(client: TestClient) -> None:
    response = client.get("/admin/connectors/catalog/test")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "test"
    assert body["display_name"] == "Test Connector"
    assert (
        body["description"]
        == "Provides a simple connector for validating configuration and MCP publishing flows"
    )
    assert body["extension"] == {"source": "built-in", "package": None}
    assert body["publication_status"] == "unconfigured"

    echo_tool = _tool_by_operation_name(body, "echo")
    assert echo_tool["operation_name"] == "echo"
    assert echo_tool["label"] == "Echo"
    assert echo_tool["description"] == "Echo a message through the configured Test Connector."
    assert echo_tool["parameters"] == {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Message to echo through the Test Connector.",
            }
        },
        "required": ["message"],
    }


def test_connector_detail_emits_present_output_schema_and_omits_absent_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    registration = copy.deepcopy(TestConnectorPlugin.registration())
    descriptions = registration["tool_descriptions"]
    descriptions[0]["output_schema_status"] = "present"
    descriptions[0]["output_schema"] = {
        "type": "object",
        "properties": {"echoed": {"type": "string"}},
    }
    descriptions[1]["output_schema_status"] = "absent"
    descriptions[1].pop("output_schema", None)
    client = TestClient(create_app(connector_registrations=[registration]))

    response = client.get("/admin/connectors/catalog/test")

    assert response.status_code == 200
    present = _tool_by_operation_name(response.json(), descriptions[0]["operation_name"])
    absent = _tool_by_operation_name(response.json(), descriptions[1]["operation_name"])
    assert present["output_schema_status"] == "present"
    assert present["output_schema"] == {
        "type": "object",
        "properties": {"echoed": {"type": "string"}},
    }
    assert absent["output_schema_status"] == "absent"
    assert "output_schema" not in absent


def test_api_consumer_views_published_connector_status_with_tools(client: TestClient) -> None:
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

    response = client.get("/admin/connectors/catalog/test")

    assert response.status_code == 200
    body = response.json()
    assert body["publication_status"] == "published"
    assert {tool["operation_name"] for tool in body["tools"]} == {"get_default_response", "echo"}


def test_available_connector_tool_without_explicit_label_has_derived_label(
    client: TestClient,
) -> None:
    response = client.get("/admin/connectors/catalog/test")

    assert response.status_code == 200
    tool = _tool_by_operation_name(response.json(), "get_default_response")
    assert tool["operation_name"] == "get_default_response"
    assert tool["label"] == "Get default response"


def test_unknown_connector_returns_helpful_not_found(client: TestClient) -> None:
    response = client.get("/admin/connectors/catalog/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Connector missing was not found"}


def test_registered_but_unavailable_connector_returns_helpful_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    client = TestClient(
        create_app(
            connector_registrations=[
                TestConnectorPlugin.registration(),
                SlackConnectorPlugin.registration(),
            ]
        )
    )

    response = client.get("/admin/connectors/catalog/slack")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Connector slack is registered but not available in this deployment"
    }


def test_unconfigured_available_connector_still_exposes_tool_metadata_without_secrets(
    client: TestClient,
) -> None:
    response = client.get("/admin/connectors/catalog/test")

    assert response.status_code == 200
    body = response.json()
    assert body["publication_status"] == "unconfigured"
    assert {tool["operation_name"] for tool in body["tools"]} == {"get_default_response", "echo"}
    assert "api_key" not in json.dumps(body)


def _tool_by_operation_name(body: dict[str, Any], operation_name: str) -> dict[str, Any]:
    return next(tool for tool in body["tools"] if tool["operation_name"] == operation_name)
