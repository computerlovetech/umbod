import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "connector-availability.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


def _settings(database_path: Path, *limits: int) -> APISettings:
    import_limit = limits[0] if limits else 10_485_760
    return APISettings(
        connector_store={"type": "sqlite", "sqlite_path": str(database_path)},
        openapi_connectors={"json_import_max_bytes": import_limit},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
    )


def _document(*operation_ids: str) -> dict[str, Any]:
    selected_operation_ids = operation_ids or ("listItems",)
    return {
        "openapi": "3.1.0",
        "info": {"title": "Example", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            f"/{operation_id}": {
                "get": {
                    "operationId": operation_id,
                    "summary": operation_id,
                    "responses": {"200": {"description": "ok"}},
                }
            }
            for operation_id in selected_operation_ids
        },
    }


def _import_current_catalog(
    client: TestClient, connector_id: str, *operation_ids: str
) -> dict[str, Any]:
    imported = client.post(
        f"/admin/connectors/openapi/{connector_id}/imports",
        json={"document": _document(*operation_ids), "approved_hosts": ["api.example.com"]},
    )
    assert imported.status_code == 201
    return imported.json()


def _set_activations(
    client: TestClient,
    connector_id: str,
    operation_ids: tuple[str, ...],
    activation_status: str,
) -> dict[str, Any]:
    response = client.put(
        f"/admin/connectors/openapi/{connector_id}/tools/activation",
        json={
            "tools": [
                {"tool_id": operation_id, "activation_status": activation_status}
                for operation_id in operation_ids
            ]
        },
    )
    assert response.status_code == 200
    return response.json()


def _publish_and_enable(client: TestClient, connector_id: str, *operation_ids: str) -> None:
    assert client.put(f"/admin/connectors/openapi/{connector_id}/publication").status_code == 200
    _set_activations(client, connector_id, operation_ids, "enabled")


def _assignable_targets(client: TestClient) -> dict[str, Any]:
    response = client.get("/admin/mcp-permissions/assignable-targets")
    assert response.status_code == 200
    return response.json()


def _create(client: TestClient, *display_names: str) -> dict[str, Any]:
    display_name = display_names[0] if display_names else "Example"
    response = client.post(
        "/admin/connectors/openapi",
        json={
            "display_name": display_name,
            "tool_name_prefix": "example_api",
            "capability_description": "Manage example API resources",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_openapi_exposes_only_batch_tool_activation(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )

    response = client.get("/admin/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths["/connectors/openapi/{connector_id}/tools/activation"]) == {"get", "put"}
    assert "/connectors/openapi/{connector_id}/tools/{tool_id}/activation" not in paths
    assert "/connectors/openapi/{connector_id}/tools/invocation-policy" not in paths


def test_create_rejects_invalid_tool_name_prefix(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )

    response = client.post(
        "/admin/connectors/openapi",
        json={
            "display_name": "Example",
            "tool_name_prefix": "invalid prefix!",
            "capability_description": "Manage example API resources",
        },
    )

    assert response.status_code == 422


def _publication_status(client: TestClient, connector_id: str) -> str:
    response = client.get(f"/admin/connectors/openapi/{connector_id}")
    assert response.status_code == 200
    return str(response.json()["publication_status"])


def test_configuration_routes_mask_encrypt_and_preserve_bearer_token(tmp_path: Path) -> None:
    database_path = tmp_path / "api.sqlite3"
    client = TestClient(create_app(settings=_settings(database_path), connector_registrations=[]))
    connector = _create(client)
    path = f"/admin/connectors/openapi/{connector['connector_id']}/configuration"

    initial = client.get(path)
    saved = client.put(path, json={"bearer_token": "private-token"})
    preserved = client.put(path, json={"bearer_token": "   "})

    assert initial.json() == {
        "configured": False,
        "authentication_type": "none",
        "masked_token": None,
    }
    expected_masked = {
        "configured": True,
        "authentication_type": "bearer",
        "masked_token": "********",
    }
    assert saved.status_code == 200
    assert saved.json() == expected_masked
    assert preserved.json() == expected_masked
    assert "private-token" not in saved.text
    with sqlite3.connect(database_path) as database:
        rows = database.execute("SELECT ciphertext FROM connector_configurations").fetchall()
    assert len(rows) == 1
    assert "private-token" not in str(rows[0][0])


def test_configuration_routes_return_not_found_without_leaking_input(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )

    response = client.put(
        "/admin/connectors/openapi/missing/configuration",
        json={"bearer_token": "must-not-leak"},
    )

    assert response.status_code == 404
    assert "must-not-leak" not in response.text


def test_admin_can_create_list_and_get_connector(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )

    second = _create(client, "Second")
    first = _create(client, "First")

    listed = client.get("/admin/connectors/openapi")
    detail = client.get(f"/admin/connectors/openapi/{first['connector_id']}")
    assert listed.status_code == 200
    assert [item["connector_id"] for item in listed.json()["connectors"]] == sorted(
        [first["connector_id"], second["connector_id"]]
    )
    assert set(listed.json()["connectors"][0]) == {
        "connector_id",
        "display_name",
        "publication_status",
        "available_actions",
    }
    assert detail.json() == first
    assert set(detail.json()) == {
        "connector_id",
        "display_name",
        "tool_name_prefix",
        "capability_description",
        "base_capability_description",
        "effective_capability_description",
        "capability_description_override",
        "created_at",
        "updated_at",
        "publication_status",
        "available_actions",
    }


def test_created_connector_starts_unconfigured_and_import_moves_to_draft(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector = _create(client)
    assert connector["publication_status"] == "unconfigured"
    assert connector["available_actions"] == ["import"]

    imported = _import_current_catalog(client, connector["connector_id"])

    assert imported["catalog_id"]
    assert imported["operation_ids"] == ["listItems"]
    assert imported["selected_server_url"] == "https://api.example.com"
    assert imported["approved_hosts"] == ["api.example.com"]
    assert _publication_status(client, connector["connector_id"]) == "draft"


def test_json_import_normalizes_deduplicates_and_ignores_blank_approved_hosts(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector = _create(client)

    response = client.post(
        f"/admin/connectors/openapi/{connector['connector_id']}/imports",
        json={
            "document": _document(),
            "approved_hosts": [
                "  API.EXAMPLE.COM  ",
                "api.example.com",
                " ",
                "CDN.EXAMPLE.COM",
                "",
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["approved_hosts"] == ["api.example.com", "cdn.example.com"]


def test_json_import_rejects_all_blank_approved_hosts(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector = _create(client)

    response = client.post(
        f"/admin/connectors/openapi/{connector['connector_id']}/imports",
        json={"document": _document(), "approved_hosts": ["", "   "]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "Approved hosts must contain exact hostnames"


def test_admin_can_import_publish_and_activate_connector(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector = _create(client)
    connector_id = connector["connector_id"]
    _import_current_catalog(client, connector_id)

    published = client.put(f"/admin/connectors/openapi/{connector_id}/publication")
    enabled = _set_activations(client, connector_id, ("listItems",), "enabled")

    assert published.status_code == 200
    assert published.json()["publication_status"] == "published"
    assert enabled["tools"] == [{"tool_id": "listItems", "activation_status": "enabled", "invocation_mode": "direct", "policy_revision": 0}]
    assert _publication_status(client, connector_id) == "published"


def test_openapi_activation_route_supports_partial_combined_and_revision_updates(tmp_path: Path) -> None:
    client = TestClient(create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[]))
    connector_id = _create(client)["connector_id"]
    _import_current_catalog(client, connector_id)
    path = f"/admin/connectors/openapi/{connector_id}/tools/activation"

    policy_only = client.put(path, json={"tools": [{"tool_id": "listItems", "invocation_mode": "ask", "expected_policy_revision": 0}]})
    activation_only = client.put(path, json={"tools": [{"tool_id": "listItems", "activation_status": "enabled"}]})
    combined = client.put(path, json={"tools": [{"tool_id": "listItems", "activation_status": "disabled", "invocation_mode": "direct", "expected_policy_revision": 1}]})

    assert policy_only.json()["tools"] == [{"tool_id": "listItems", "activation_status": "disabled", "invocation_mode": "ask", "policy_revision": 1}]
    assert activation_only.json()["tools"] == [{"tool_id": "listItems", "activation_status": "enabled", "invocation_mode": "ask", "policy_revision": 1}]
    assert combined.json()["tools"] == [{"tool_id": "listItems", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 2}]


def test_openapi_activation_route_handles_noop_conflict_and_unknown_atomically(tmp_path: Path) -> None:
    client = TestClient(create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[]))
    connector_id = _create(client)["connector_id"]
    _import_current_catalog(client, connector_id)
    path = f"/admin/connectors/openapi/{connector_id}/tools/activation"

    direct = client.put(path, json={"tools": [{"tool_id": "listItems", "invocation_mode": "direct", "expected_policy_revision": 0}]})
    stale = client.put(path, json={"tools": [{"tool_id": "listItems", "invocation_mode": "ask", "expected_policy_revision": 1}]})
    unknown = client.put(path, json={"tools": [{"tool_id": "listItems", "activation_status": "enabled"}, {"tool_id": "missing", "invocation_mode": "ask", "expected_policy_revision": 0}]})

    assert direct.json()["tools"][0]["policy_revision"] == 0
    assert stale.status_code == 409
    assert stale.json() == {"code": "invocation_policy_revision_conflict", "conflicts": [{"tool_id": "listItems", "expected_revision": 1, "current_mode": "direct", "current_revision": 0}]}
    assert unknown.status_code == 404
    assert client.get(path).json()["tools"][0] == {"tool_id": "listItems", "activation_status": "disabled", "invocation_mode": "direct", "policy_revision": 0}


@pytest.mark.parametrize("item", [{"tool_id": "listItems"}, {"tool_id": "listItems", "invocation_mode": "ask"}, {"tool_id": "listItems", "expected_policy_revision": 0}, {"tool_id": "listItems", "invocation_mode": "ask", "expected_policy_revision": -1}])
def test_openapi_activation_route_rejects_malformed_partial_items(tmp_path: Path, item: dict[str, Any]) -> None:
    client = TestClient(create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[]))
    connector_id = _create(client)["connector_id"]
    _import_current_catalog(client, connector_id)
    path = f"/admin/connectors/openapi/{connector_id}/tools/activation"
    response = client.put(path, json={"tools": [item]})
    duplicate = client.put(path, json={"tools": [{"tool_id": "listItems", "activation_status": "enabled"}, {"tool_id": "listItems", "activation_status": "disabled"}]})
    assert response.status_code == 422
    assert duplicate.status_code == 422


def test_openapi_connector_assignability_follows_publication_and_tool_activation(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    with client:
        connector = _create(client)
        connector_id = connector["connector_id"]
        _import_current_catalog(client, connector_id, "readItems")
        assert _assignable_targets(client) == {"connectors": [], "capabilities": []}

        assert (
            client.put(f"/admin/connectors/openapi/{connector_id}/publication").status_code == 200
        )
        assert _assignable_targets(client) == {"connectors": [], "capabilities": []}

        _set_activations(client, connector_id, ("readItems",), "enabled")
        assert _assignable_targets(client) == {
            "connectors": [{"connector_id": connector_id, "display_name": "Example"}],
            "capabilities": [
                {
                    "connector_id": connector_id,
                    "capability_kind": "tool",
                    "capability_key": "readItems",
                    "display_name": "readItems",
                }
            ],
        }

        _set_activations(client, connector_id, ("readItems",), "disabled")
        assert _assignable_targets(client) == {"connectors": [], "capabilities": []}

        response = client.delete(f"/admin/connectors/openapi/{connector_id}/publication")
        assert response.status_code == 200
        assert response.json()["publication_status"] == "unpublished"
        assert _assignable_targets(client) == {"connectors": [], "capabilities": []}


def test_invalid_candidate_returns_structured_issues(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector = _create(client)

    response = client.post(
        f"/admin/connectors/openapi/{connector['connector_id']}/imports",
        json={"document": {"openapi": "2.0"}, "approved_hosts": ["api.example.com"]},
    )

    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert issues
    assert set(issues[0]) == {"code", "location", "message"}


def test_unknown_connector_returns_404(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    assert client.get("/admin/connectors/openapi/missing").status_code == 404


def test_unknown_connector_import_returns_404(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    response = client.post(
        "/admin/connectors/openapi/missing/imports",
        json={"document": _document(), "approved_hosts": ["api.example.com"]},
    )
    assert response.status_code == 404


def test_malformed_request_returns_422(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    assert client.post("/admin/connectors/openapi", json={}).status_code == 422


def test_json_import_rejects_request_over_configured_limit(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3", 100), connector_registrations=[])
    )
    connector = _create(client)
    response = client.post(
        f"/admin/connectors/openapi/{connector['connector_id']}/imports",
        content=json.dumps({"document": _document(), "approved_hosts": ["api.example.com"]}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "openapi_import_too_large", "max_bytes": 100}}


def test_connectors_persist_across_app_recreation(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "api.sqlite3")
    first_client = TestClient(create_app(settings=settings, connector_registrations=[]))
    connector = _create(first_client)

    second_client = TestClient(create_app(settings=settings, connector_registrations=[]))

    assert (
        second_client.get(f"/admin/connectors/openapi/{connector['connector_id']}").json()
        == connector
    )


def test_openapi_connector_routes_are_admin_protected(tmp_path: Path) -> None:
    settings = APISettings(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "api.sqlite3")},
        admin_authentication={
            "mode": "jwt",
            "jwks_url": "https://identity.example/.well-known/jwks.json",
        },
    )
    client = TestClient(create_app(settings=settings, connector_registrations=[]))
    assert client.get("/admin/connectors/openapi").status_code == 401
