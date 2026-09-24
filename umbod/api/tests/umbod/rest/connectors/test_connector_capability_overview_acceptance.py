import json
from pathlib import Path
from typing import Any, cast

from tests.support.connector_capabilities import CapabilityKind

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.core.connectors.downstream_mcp.probe import (
    DiscoveredCapabilities,
    ProbeCapabilities,
    ScriptedDownstreamMcpProbe,
)
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings
from tests.support.connector_plugins import TestConnectorPlugin
from tests.support.connector_capabilities import ConnectorCapabilityAdminDriver


@pytest.fixture
def programmed_driver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> ConnectorCapabilityAdminDriver:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    registration = TestConnectorPlugin.registration()
    registration["prompt_descriptions"] = [
        {
            "name": "summarize",
            "description": "Summarize an article.",
            "arguments": [
                {
                    "name": "article_id",
                    "description": "Article identifier.",
                    "required": True,
                }
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
    client = TestClient(create_app(connector_registrations=[registration]))
    return ConnectorCapabilityAdminDriver(client)


@pytest.fixture
def proxied_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ConnectorCapabilityAdminDriver, str]:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    settings = APISettings(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "api.sqlite3")},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
    )
    app = create_app(settings=settings, connector_registrations=[])
    probe = ScriptedDownstreamMcpProbe(
        (
            ProbeCapabilities(
                capabilities=DiscoveredCapabilities(tools=()),
                endpoint_url="https://example.test/mcp",
            ),
        )
    )

    def probe_override() -> ScriptedDownstreamMcpProbe:
        return probe

    admin_app = cast(FastAPI, next(route.app for route in app.routes if route.path == "/admin"))
    admin_app.dependency_overrides[get_downstream_connector_probe] = probe_override
    client = TestClient(app)
    payload: dict[str, Any] = {
        "metadata": {
            "display_name": "Knowledge Base",
            "capability_description": "Read knowledge base content",
            "public_path": "/mcp/proxies/knowledge-base",
        },
        "configuration": {
            "endpoint_url": "https://example.test/mcp",
            "auth_mode": "static_bearer",
            "bearer_token": "secret",
        },
    }
    connector_id = client.post("/admin/connectors/mcp", json=payload).json()["connector_id"]
    return ConnectorCapabilityAdminDriver(client), connector_id


def test_programmed_connector_prompt_catalog_exposes_metadata_separately(
    programmed_driver: ConnectorCapabilityAdminDriver,
) -> None:
    response = programmed_driver.programmed_catalog("test", "prompts")

    assert response.status_code == 200
    assert response.body == {
        "prompts": [
            {
                "name": "summarize",
                "description": "Summarize an article.",
                "arguments": [
                    {
                        "name": "article_id",
                        "description": "Article identifier.",
                        "required": True,
                    }
                ],
                "activation_status": "disabled",
            }
        ],
        "available_actions": ["activate"],
    }
    assert "tools" not in response.body


def test_programmed_connector_resource_catalog_distinguishes_templates(
    programmed_driver: ConnectorCapabilityAdminDriver,
) -> None:
    response = programmed_driver.programmed_catalog("test", "resources")

    assert response.status_code == 200
    assert {item["kind"] for item in response.body["resources"]} == {
        "resource",
        "resource_template",
    }
    assert "tools" not in response.body


@pytest.mark.parametrize("capability_kind", ["prompts", "resources"])
def test_new_proxied_connector_has_empty_read_only_capability_catalogs(
    proxied_driver: tuple[ConnectorCapabilityAdminDriver, str], capability_kind: CapabilityKind
) -> None:
    driver, connector_id = proxied_driver

    response = driver.proxied_catalog(connector_id, capability_kind)

    assert response.status_code == 200
    assert response.body[capability_kind] == []
    assert response.body["available_actions"] == []
    assert "tools" not in response.body
