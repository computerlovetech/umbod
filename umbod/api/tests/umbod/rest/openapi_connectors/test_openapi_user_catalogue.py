from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.core.connectors.downstream_mcp.stores import DownstreamMcpStores
from umbod.rest.user_catalogue.dependencies import get_personal_catalogue_store_supplier
from umbod.rest.user_catalogue.ports import PersonalCatalogueStoreSupplier

from test_simplified_openapi_connector_target import (
    _create_connector, _document, _import, _set_activation, _set_publication,
    client as client, connector_availability as connector_availability,
)


class ForbiddenPersonalCatalogueStoreSupplier:
    async def create(self) -> DownstreamMcpStores:
        raise AssertionError("Personal dependencies must remain unresolved")


@pytest.fixture
def forbidden_personal_stores(client: TestClient) -> Iterator[None]:
    root = cast(FastAPI, client.app)
    app = next(route.app for route in root.routes if getattr(route, "path", "") == "/api/me")

    def supplier() -> PersonalCatalogueStoreSupplier:
        return ForbiddenPersonalCatalogueStoreSupplier()

    app.dependency_overrides[get_personal_catalogue_store_supplier] = supplier
    try:
        yield
    finally:
        del app.dependency_overrides[get_personal_catalogue_store_supplier]


def test_personal_disabled_local_catalogue_uses_explicit_current_capability_grants(
    client: TestClient, forbidden_personal_stores: None,
) -> None:
    connector_id = _create_connector(client)
    _import(client, connector_id, _document(
        ("listItems", "get", "/items", "Display title", "Public description"),
    ))
    _set_activation(client, connector_id, "listItems", True)
    _set_publication(client, connector_id, True)
    permissions = "/api/admin/mcp-permissions/groups/umbod-admins/permissions"
    client.put(permissions, json={"connectors": [
        {"connector_id": connector_id, "permission_status": "enabled"},
    ]}).raise_for_status()
    response = client.get("/api/me/catalogue")
    assert response.status_code == 200
    assert response.json()["personal_enabled"] is False
    assert response.json()["connectors"] == []
    client.put(permissions, json={"capabilities": [{
        "connector_id": connector_id, "capability_kind": "tool",
        "capability_key": "listItems", "permission_status": "enabled",
    }]}).raise_for_status()
    response = client.get("/api/me/catalogue")
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["connectors"] == [{
        "connector_id": connector_id, "kind": "openapi", "display_name": "Inventory",
        "capability_description": "Manage inventory resources", "ownership": "shared",
        "capabilities": [{
            "kind": "tool", "key": "listItems", "name": "Display title",
            "description": "Public description",
            "input_schema": {
                "type": "object",
                "properties": {
                    "connector_id": {"type": "string", "const": connector_id},
                    "operation_id": {"type": "string", "const": "listItems"},
                    **{location: {
                        "type": "object", "properties": {}, "required": [], "additionalProperties": False,
                    } for location in ("path", "query", "headers")},
                    "body": {
                        "description": "Tagged JSON body. Use state 'missing' or state 'present' with value.",
                        "oneOf": [
                            {"type": "object", "properties": {"state": {"const": "missing"}}, "required": ["state"]},
                            {"type": "object", "properties": {"state": {"const": "present"}, "value": {}},
                             "required": ["state", "value"]},
                        ],
                    },
                },
                "required": ["connector_id", "operation_id", "path", "query", "headers", "body"],
            },
            "output_schema": {"status": "absent"},
        }],
    }]
    _set_activation(client, connector_id, "listItems", False)
    assert client.get("/api/me/catalogue").json()["connectors"] == []
    assert client.get("/api/me/connectors/mcp").status_code == 404
