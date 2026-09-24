import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ConfigDict, SecretStr
from umbod.core.connectors.native.models import ConnectorConfigurationCheckResult
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
                    "capability_description": "Access connector capabilities.",
                    "description": "Connects to Slack workspaces and channels",
                    "extension": {"source": "built-in"},
                    "configuration_schema": SlackAdminConfiguration,
                    "configuration_check": check_slack_configuration,
                },
                {
                    "id": "github",
                    "display_name": "GitHub",
                    "capability_description": "Access connector capabilities.",
                    "description": "Connects to GitHub repositories and issues",
                    "extension": {"source": "built-in"},
                    "configuration_schema": SlackAdminConfiguration,
                },
            ]
        )
    )


def test_admin_gets_schema_driven_configuration_form_definition(client: TestClient) -> None:
    response = client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 200
    assert response.json() == slack_configuration_form_definition()


def test_default_built_in_slack_connector_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "slack"}]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    default_client = TestClient(create_app())

    response = default_client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 200
    assert response.json() == slack_configuration_form_definition()


def test_default_built_in_test_connector_is_available_for_flow_testing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    default_client = TestClient(create_app())

    response = default_client.get("/admin/connectors/catalog/test/configuration")

    assert response.status_code == 200
    assert response.json() == {
        "connector": {"id": "test", "display_name": "Test Connector"},
        "schema": {
            "fields": [
                {"name": "instance_name", "type": "string", "required": True, "secret": False},
                {"name": "api_key", "type": "string", "required": True, "secret": True},
                {"name": "default_response", "type": "string", "required": True, "secret": False},
            ]
        },
        "configuration": None,
    }


def test_admin_creates_current_global_configuration_without_reading_back_secret(
    client: TestClient,
) -> None:
    response = client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-secret",
                "default_channel_id": "C123",
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "slack",
        "status": "configured",
        "configuration": {
            "workspace_name": "Acme",
            "bot_token": "**********",
            "default_channel_id": "C123",
        },
    }
    assert "xoxb-secret" not in response.text


def test_admin_updates_current_global_configuration_and_replaces_secret(client: TestClient) -> None:
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

    response = client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": "Acme Europe",
                "bot_token": "xoxb-replacement",
                "default_channel_id": "C456",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["configuration"] == {
        "workspace_name": "Acme Europe",
        "bot_token": "**********",
        "default_channel_id": "C456",
    }
    assert "xoxb-replacement" not in response.text


def test_admin_views_existing_configuration_with_masked_secret(client: TestClient) -> None:
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

    response = client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 200
    assert response.json()["configuration"] == {
        "workspace_name": "Acme",
        "bot_token": "**********",
        "default_channel_id": "C123",
    }
    assert "xoxb-secret" not in response.text


def test_admin_updates_non_secret_fields_without_replacing_existing_secret(
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

    response = client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={"configuration": {"workspace_name": "Acme Support", "default_channel_id": "C789"}},
    )

    assert response.status_code == 200
    assert response.json()["configuration"] == {
        "workspace_name": "Acme Support",
        "bot_token": "**********",
        "default_channel_id": "C789",
    }
    assert "xoxb-secret" not in response.text


@pytest.mark.parametrize(
    ("payload", "field_name"),
    [
        ({"workspace_name": "Acme", "bot_token": "xoxb-secret"}, "default_channel_id"),
        (
            {
                "workspace_name": "Acme",
                "bot_token": "xoxb-secret",
                "default_channel_id": "C123",
                "admin_override": True,
            },
            "admin_override",
        ),
    ],
)
def test_admin_sees_schema_validation_errors_without_changing_current_configuration(
    client: TestClient,
    payload: dict[str, Any],
    field_name: str,
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

    response = client.put(
        "/admin/connectors/catalog/slack/configuration", json={"configuration": payload}
    )
    current_response = client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 422
    assert field_name in response.text
    assert current_response.json()["configuration"] == {
        "workspace_name": "Acme",
        "bot_token": "**********",
        "default_channel_id": "C123",
    }


def test_admin_cannot_save_configuration_with_invalid_field_data_types(client: TestClient) -> None:
    response = client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": 123,
                "bot_token": "xoxb-secret",
                "default_channel_id": "C123",
            }
        },
    )

    assert response.status_code == 422
    assert "workspace_name" in response.text
    assert "Input should be a valid string" in response.text


def test_admin_cannot_configure_connector_that_is_not_available(client: TestClient) -> None:
    response = client.get("/admin/connectors/catalog/github/configuration")

    assert response.status_code == 404
    assert response.json() == {"detail": "Connector is not available for configuration"}


def test_admin_checks_valid_configuration_without_saving_it(client: TestClient) -> None:
    response = client.post(
        "/admin/connectors/catalog/slack/configuration/validations",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-valid",
                "default_channel_id": "C123",
            }
        },
    )
    current_response = client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 200
    assert response.json() == {"valid": True, "message": None, "field_messages": {}}
    assert current_response.json()["configuration"] is None


def test_admin_checks_invalid_configuration_without_saving_it(client: TestClient) -> None:
    response = client.post(
        "/admin/connectors/catalog/slack/configuration/validations",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "invalid-token",
                "default_channel_id": "C123",
            }
        },
    )
    current_response = client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 200
    assert response.json() == {
        "valid": False,
        "message": "Slack bot token is invalid.",
        "field_messages": {"bot_token": "Use a valid Slack bot token."},
    }
    assert current_response.json()["configuration"] is None


def test_admin_checks_configuration_with_existing_secret_when_secret_is_omitted(
    client: TestClient,
) -> None:
    client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-valid",
                "default_channel_id": "C123",
            }
        },
    )

    response = client.post(
        "/admin/connectors/catalog/slack/configuration/validations",
        json={"configuration": {"workspace_name": "Acme Support", "default_channel_id": "C789"}},
    )

    assert response.status_code == 200
    assert response.json() == {"valid": True, "message": None, "field_messages": {}}


def test_admin_sees_schema_validation_errors_when_checking_configuration(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/connectors/catalog/slack/configuration/validations",
        json={"configuration": {"workspace_name": "Acme", "bot_token": "xoxb-valid"}},
    )

    assert response.status_code == 422
    assert "default_channel_id" in response.text


def test_admin_cannot_check_configuration_for_connector_that_is_not_available(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/connectors/catalog/github/configuration/validations",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-valid",
                "default_channel_id": "C123",
            }
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Connector is not available for configuration"}


def check_slack_configuration(
    configuration: SlackAdminConfiguration,
) -> ConnectorConfigurationCheckResult:
    if configuration.bot_token.get_secret_value() == "xoxb-valid":
        return ConnectorConfigurationCheckResult(valid=True)
    return ConnectorConfigurationCheckResult(
        valid=False,
        message="Slack bot token is invalid.",
        field_messages={"bot_token": "Use a valid Slack bot token."},
    )


def slack_configuration_form_definition() -> dict[str, Any]:
    return {
        "connector": {
            "id": "slack",
            "display_name": "Slack",
        },
        "schema": {
            "fields": [
                {"name": "workspace_name", "type": "string", "required": True, "secret": False},
                {"name": "bot_token", "type": "string", "required": True, "secret": True},
                {"name": "default_channel_id", "type": "string", "required": True, "secret": False},
            ]
        },
        "configuration": None,
    }


def test_current_global_configuration_is_in_memory_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "slack"}]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    registrations = [
        {
            "id": "slack",
            "display_name": "Slack",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to Slack workspaces and channels",
            "extension": {"source": "built-in"},
            "configuration_schema": SlackAdminConfiguration,
        }
    ]
    first_client = TestClient(create_app(connector_registrations=registrations))
    first_client.put(
        "/admin/connectors/catalog/slack/configuration",
        json={
            "configuration": {
                "workspace_name": "Acme",
                "bot_token": "xoxb-secret",
                "default_channel_id": "C123",
            }
        },
    )

    restarted_client = TestClient(create_app(connector_registrations=registrations))
    response = restarted_client.get("/admin/connectors/catalog/slack/configuration")

    assert response.status_code == 200
    assert response.json()["configuration"] is None
