from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@dataclass(frozen=True)
class AvailabilityCase:
    published: bool
    enabled: bool
    permitted: bool
    available: bool


@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "connector-availability.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = APISettings(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "api.sqlite3")},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
    )
    with TestClient(create_app(settings=settings, connector_registrations=[])) as test_client:
        yield test_client


def _document(*operations: tuple[str, str, str, str, str]) -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    for operation_id, method, path, summary, description in operations:
        paths.setdefault(path, {})[method] = {
            "operationId": operation_id,
            "summary": summary,
            "description": description,
            "responses": {"200": {"description": "ok"}},
        }
    return {
        "openapi": "3.1.0",
        "info": {"title": "Inventory", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": paths,
    }


def _create_connector(client: TestClient) -> str:
    response = client.post(
        "/admin/connectors/openapi",
        json={"display_name": "Inventory", "capability_description": "Manage inventory resources"},
    )
    assert response.status_code == 201
    return str(response.json()["connector_id"])


def _import(client: TestClient, connector_id: str, document: dict[str, Any]) -> None:
    response = client.post(
        f"/admin/connectors/openapi/{connector_id}/imports",
        json={"document": document, "approved_hosts": ["api.example.com"]},
    )
    assert response.status_code == 201


def _tools(client: TestClient, connector_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/admin/connectors/openapi/{connector_id}/tools")
    assert response.status_code == 200
    return list(response.json()["tools"])


def _set_activation(
    client: TestClient, connector_id: str, operation_id: str, enabled: bool
) -> None:
    response = client.put(
        f"/admin/connectors/openapi/{connector_id}/tools/activation",
        json={
            "tools": [
                {
                    "tool_id": operation_id,
                    "activation_status": "enabled" if enabled else "disabled",
                }
            ]
        },
    )
    assert response.status_code == 200


def _activation_statuses(client: TestClient, connector_id: str) -> dict[str, str]:
    return {
        str(tool["operation_id"]): str(tool["activation_status"])
        for tool in _tools(client, connector_id)
    }


def _enable_operations(
    client: TestClient, connector_id: str, operation_ids: tuple[str, ...]
) -> None:
    for operation_id in operation_ids:
        _set_activation(client, connector_id, operation_id, True)


def _set_publication(client: TestClient, connector_id: str, published: bool) -> None:
    path = f"/admin/connectors/openapi/{connector_id}/publication"
    response = client.put(path) if published else client.delete(path)
    assert response.status_code == 200


def test_import_immediately_replaces_catalog_with_concise_disabled_operation_metadata(
    client: TestClient,
) -> None:
    connector_id = _create_connector(client)
    _import(
        client,
        connector_id,
        _document(("listItems", "get", "/items", "List items", "Returns inventory items")),
    )

    assert _tools(client, connector_id) == [
        {
            "operation_id": "listItems",
            "method": "GET",
            "path": "/items",
            "summary": "List items",
            "description": "Returns inventory items",
            "activation_status": "disabled",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "output_schema_status": "absent",
        }
    ]


def test_operations_can_be_activated_independently(client: TestClient) -> None:
    connector_id = _create_connector(client)
    _import(
        client,
        connector_id,
        _document(
            ("listItems", "get", "/items", "List", "Lists items"),
            ("createItem", "post", "/items", "Create", "Creates an item"),
        ),
    )

    _set_activation(client, connector_id, "listItems", True)

    assert _activation_statuses(client, connector_id) == {
        "listItems": "enabled",
        "createItem": "disabled",
    }


def test_reimport_with_connector_permission_reconciles_catalog_and_preserves_grant(
    client: TestClient,
) -> None:
    connector_id = _create_connector(client)
    first = _document(
        ("stable", "get", "/stable", "Stable", "Stable operation"),
        ("removed", "get", "/removed", "Removed", "Removed operation"),
    )
    _import(client, connector_id, first)
    _enable_operations(client, connector_id, ("stable", "removed"))
    grant = client.put(
        "/admin/mcp-permissions/groups/engineering/permissions",
        json={
            "connectors": [{"connector_id": connector_id, "permission_status": "enabled"}],
            "capabilities": [],
        },
    )
    assert grant.status_code == 200
    replacement = _document(
        ("stable", "get", "/stable", "Updated stable", "Updated description"),
        ("new", "post", "/new", "New", "New operation"),
    )

    _import(client, connector_id, replacement)

    assert _tools(client, connector_id) == [
        {
            "operation_id": "new",
            "method": "POST",
            "path": "/new",
            "summary": "New",
            "description": "New operation",
            "activation_status": "disabled",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "output_schema_status": "absent",
        },
        {
            "operation_id": "stable",
            "method": "GET",
            "path": "/stable",
            "summary": "Updated stable",
            "description": "Updated description",
            "activation_status": "enabled",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "output_schema_status": "absent",
        },
    ]
    _import(client, connector_id, first)
    assert _activation_statuses(client, connector_id) == {
        "stable": "enabled",
        "removed": "disabled",
    }
    group = client.get("/admin/mcp-permissions/groups/engineering")
    assert group.status_code == 200
    assert group.json()["connector_ids"] == [connector_id]


def test_permission_conflict_rejects_removal_without_changing_current_catalog(
    client: TestClient,
) -> None:
    connector_id = _create_connector(client)
    original = _document(("readItems", "get", "/items", "Read", "Reads items"))
    _import(client, connector_id, original)
    grant = client.put(
        "/admin/mcp-permissions/groups/engineering/permissions",
        json={
            "connectors": [],
            "capabilities": [
                {
                    "connector_id": connector_id,
                    "capability_kind": "tool",
                    "capability_key": "readItems",
                    "permission_status": "enabled",
                }
            ],
        },
    )
    assert grant.status_code == 200

    conflict = client.post(
        f"/admin/connectors/openapi/{connector_id}/imports",
        json={
            "document": _document(("writeItems", "post", "/items", "Write", "Writes items")),
            "approved_hosts": ["api.example.com"],
        },
    )

    assert conflict.status_code == 409
    assert [tool["operation_id"] for tool in _tools(client, connector_id)] == ["readItems"]


def test_failed_import_leaves_current_catalog_and_activation_unchanged(client: TestClient) -> None:
    connector_id = _create_connector(client)
    _import(client, connector_id, _document(("readItems", "get", "/items", "Read", "Reads")))
    _set_activation(client, connector_id, "readItems", True)

    failed = client.post(
        f"/admin/connectors/openapi/{connector_id}/imports",
        json={"document": {"openapi": "2.0"}, "approved_hosts": ["api.example.com"]},
    )

    assert failed.status_code == 422
    assert [
        (tool["operation_id"], tool["activation_status"]) for tool in _tools(client, connector_id)
    ] == [("readItems", "enabled")]


@pytest.mark.parametrize(
    "case",
    [
        AvailabilityCase(False, False, False, False),
        AvailabilityCase(True, False, True, False),
        AvailabilityCase(True, True, False, True),
        AvailabilityCase(True, True, True, True),
        AvailabilityCase(False, True, True, False),
    ],
)
def test_permission_availability_requires_publication_activation_and_grant(
    client: TestClient,
    case: AvailabilityCase,
) -> None:
    connector_id = _create_connector(client)
    _import(client, connector_id, _document(("readItems", "get", "/items", "Read", "Reads")))
    if case.enabled:
        _set_activation(client, connector_id, "readItems", True)
    if case.published:
        _set_publication(client, connector_id, True)
    if case.permitted:
        response = client.put(
            "/admin/mcp-permissions/groups/engineering/permissions",
            json={
                "connectors": [],
                "capabilities": [
                    {
                        "connector_id": connector_id,
                        "capability_kind": "tool",
                        "capability_key": "readItems",
                        "permission_status": "enabled",
                    }
                ],
            },
        )
        assert response.status_code == 200

    targets = client.get(
        "/admin/mcp-permissions/assignable-targets",
        headers={"x-simulated-groups": "engineering"},
    )

    assert targets.status_code == 200
    identities = {
        (capability["connector_id"], capability["capability_key"])
        for capability in targets.json()["capabilities"]
    }
    assert ((connector_id, "readItems") in identities) is case.available
