import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import Field
from umbod.proxies import Model

from umbod.rest.main import create_app


class RequiredConnectorConfiguration(Model):
    workspace_name: str


class DefaultedConnectorConfiguration(Model):
    workspace_name: str = "Acme"


class DefaultFactoryConnectorConfiguration(Model):
    channel_ids: list[str] = Field(default_factory=list)


def test_admin_can_discover_builtin_connectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registrations = [
        {
            "id": "github",
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub repositories and issues",
            "extension": {"source": "built-in"},
        }
    ]

    client = TestClient(
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            connector_registrations, "connectors.json"
        )
    )

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json() == {
        "connectors": [
            _unconfigured_connector(
                {
                    "id": "github",
                    "display_name": "GitHub",
                    "capability_description": "Access connector capabilities.",
                    "description": "Connects to GitHub repositories and issues",
                    "extension": {"source": "built-in", "package": None},
                }
            )
        ]
    }


def test_admin_can_discover_user_supplied_deploy_time_connectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registrations = [
        {
            "id": "linear",
            "display_name": "Linear",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to Linear issues and projects",
            "extension": {"source": "user-supplied"},
        }
    ]

    client = TestClient(
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            connector_registrations, "connectors.json"
        )
    )

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json()["connectors"] == [
        _unconfigured_connector(
            {
                "id": "linear",
                "display_name": "Linear",
                "capability_description": "Access connector capabilities.",
                "description": "Connects to Linear issues and projects",
                "extension": {"source": "user-supplied", "package": None},
            }
        )
    ]


def test_builtin_and_user_supplied_connectors_appear_in_the_same_product_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registrations = [
        {
            "id": "github",
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub repositories and issues",
            "extension": {"source": "built-in"},
        },
        {
            "id": "linear",
            "display_name": "Linear",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to Linear issues and projects",
            "extension": {"source": "user-supplied"},
        },
    ]

    client = TestClient(
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            connector_registrations, "connectors.json"
        )
    )

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json()["connectors"] == [
        _unconfigured_connector(
            {
                "id": "github",
                "display_name": "GitHub",
                "capability_description": "Access connector capabilities.",
                "description": "Connects to GitHub repositories and issues",
                "extension": {"source": "built-in", "package": None},
            }
        ),
        _unconfigured_connector(
            {
                "id": "linear",
                "display_name": "Linear",
                "capability_description": "Access connector capabilities.",
                "description": "Connects to Linear issues and projects",
                "extension": {"source": "user-supplied", "package": None},
            }
        ),
    ]


def test_admin_can_tell_when_no_connectors_are_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(_ConnectorAppBuilder(tmp_path, monkeypatch).build([], "connectors.json"))

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json() == {"connectors": []}


def test_future_connector_metadata_does_not_change_the_basic_connector_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registrations = [
        {
            "id": "github",
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub repositories and issues",
            "extension": {"source": "built-in", "package": "umbod-connectors"},
            "documentation_url": "https://example.com/connectors/github",
        }
    ]

    client = TestClient(
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            connector_registrations, "connectors.json"
        )
    )

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json()["connectors"] == [
        _unconfigured_connector(
            {
                "id": "github",
                "display_name": "GitHub",
                "capability_description": "Access connector capabilities.",
                "description": "Connects to GitHub repositories and issues",
                "extension": {"source": "built-in", "package": "umbod-connectors"},
            }
        )
    ]


@pytest.mark.parametrize(
    "invalid_connector_registration",
    [
        {
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub repositories and issues",
            "extension": {"source": "built-in"},
        },
        {
            "id": "github",
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "extension": {"source": "built-in"},
        },
    ],
)
def test_invalid_connector_metadata_fails_startup(
    invalid_connector_registration: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="connector metadata validation"):
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            [invalid_connector_registration], "connectors.json"
        )


def test_connector_without_configuration_schema_fails_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registration = {
        "id": "github",
        "display_name": "GitHub",
        "capability_description": "Access connector capabilities.",
        "description": "Connects to GitHub repositories and issues",
        "extension": {"source": "built-in"},
    }

    deployment_file = tmp_path / "connectors.json"
    deployment_file.write_text(json.dumps({"connectors": [{"id": "github"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    with pytest.raises(ValueError, match="connector github needs to have a configuration schema"):
        create_app(connector_registrations=[connector_registration])


@pytest.mark.parametrize(
    "configuration_schema",
    [DefaultedConnectorConfiguration, DefaultFactoryConnectorConfiguration],
)
def test_connector_configuration_schema_with_default_values_fails_startup(
    configuration_schema: type[Model],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registration = {
        "id": "github",
        "display_name": "GitHub",
        "capability_description": "Access connector capabilities.",
        "description": "Connects to GitHub repositories and issues",
        "extension": {"source": "built-in"},
        "configuration_schema": configuration_schema,
    }

    with pytest.raises(
        ValueError, match="connector github configuration schema must not define default values"
    ):
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            [connector_registration], "connectors.json"
        )


def test_duplicate_connector_identity_fails_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registrations = [
        {
            "id": "github",
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub repositories and issues",
            "extension": {"source": "built-in"},
        },
        {
            "id": "github",
            "display_name": "GitHub Enterprise",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub Enterprise repositories and issues",
            "extension": {"source": "user-supplied"},
        },
    ]

    with pytest.raises(ValueError, match="duplicate connector id: github"):
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            connector_registrations, "connectors.json"
        )


def test_connector_discovery_does_not_show_operation_permission_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector_registrations = [
        {
            "id": "github",
            "display_name": "GitHub",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to GitHub repositories and issues",
            "extension": {"source": "built-in"},
        }
    ]

    client = TestClient(
        _ConnectorAppBuilder(tmp_path, monkeypatch).build(
            connector_registrations, "connectors.json"
        )
    )

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert "permission_status" not in response.json()["connectors"][0]
    assert "operations" not in response.json()["connectors"][0]


def test_connector_list_reflects_the_deployed_application_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _ConnectorAppBuilder(tmp_path, monkeypatch)
    running_client = TestClient(
        builder.build([_github_connector()], file_name="running-connectors.json")
    )
    deployed_client = TestClient(
        builder.build(
            [_github_connector(), _slack_connector()], file_name="deployed-connectors.json"
        )
    )

    _assert_connector_ids(running_client, ["github"])
    _assert_connector_ids(deployed_client, ["github", "slack"])


def _github_connector() -> dict[str, Any]:
    return {
        "id": "github",
        "display_name": "GitHub",
        "capability_description": "Access connector capabilities.",
        "description": "Connects to GitHub repositories and issues",
        "extension": {"source": "built-in"},
    }


def _slack_connector() -> dict[str, Any]:
    return {
        "id": "slack",
        "display_name": "Slack",
        "capability_description": "Access connector capabilities.",
        "description": "Connects to Slack workspaces and channels",
        "extension": {"source": "user-supplied"},
    }


def _assert_connector_ids(client: TestClient, expected_connector_ids: list[str]) -> None:
    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert [
        connector["id"] for connector in response.json()["connectors"]
    ] == expected_connector_ids


def _with_configuration_schema(registration: dict[str, Any]) -> dict[str, Any]:
    if "configuration_schema" in registration or "id" not in registration:
        return registration
    return {**registration, "configuration_schema": RequiredConnectorConfiguration}


def _unconfigured_connector(connector: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": connector["id"],
        "display_name": connector["display_name"],
        "description": connector["description"],
        "extension": {"source": connector["extension"]["source"]},
        "publication_status": "unconfigured",
        "available_actions": ["configure"],
    }


class _ConnectorAppBuilder:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch

    def build(
        self,
        connector_registrations: list[dict[str, Any]],
        file_name: str,
    ) -> FastAPI:
        deployment_file = self._write_deployment_file(connector_registrations, file_name)
        self.monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))
        return create_app(
            connector_registrations=self._configured_registrations(connector_registrations)
        )

    def _write_deployment_file(
        self,
        connector_registrations: list[dict[str, Any]],
        file_name: str,
    ) -> Path:
        deployment_file = self.tmp_path / file_name
        deployment_file.write_text(
            json.dumps({"connectors": self._connector_deployment_config(connector_registrations)}),
            encoding="utf-8",
        )
        return deployment_file

    def _connector_deployment_config(
        self,
        connector_registrations: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        return [
            {"id": registration["id"]}
            for registration in connector_registrations
            if isinstance(registration.get("id"), str)
        ]

    def _configured_registrations(
        self,
        connector_registrations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            _with_configuration_schema(registration) for registration in connector_registrations
        ]
