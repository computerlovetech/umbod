import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "connector-availability.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


def _settings(database_path: Path, import_limit: int = 10_485_760) -> APISettings:
    return APISettings(
        connector_store={"type": "sqlite", "sqlite_path": str(database_path)},
        openapi_connectors={"json_import_max_bytes": import_limit},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
    )


def _document() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Example", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }


def _create(client: TestClient) -> str:
    response = client.post(
        "/admin/connectors/openapi",
        json={"display_name": "Example", "capability_description": "Manage example API resources"},
    )
    assert response.status_code == 201
    return str(response.json()["connector_id"])


def _upload(
    client: TestClient,
    connector_id: str,
    content: bytes,
    filename: str = "spec.json",
    media_type: str = "application/json",
    approved_hosts: tuple[str, ...] = ("api.example.com",),
) -> Response:
    return client.post(
        f"/admin/connectors/openapi/{connector_id}/imports",
        files={"file": (filename, content, media_type)},
        data={"approved_hosts": list(approved_hosts)},
    )


def _has_current_catalog(client: TestClient, connector_id: str) -> bool:
    response = client.get(f"/admin/connectors/openapi/{connector_id}")
    assert response.status_code == 200
    return response.json()["publication_status"] != "unconfigured"


def test_file_import_replaces_current_catalog_with_document_and_multiple_hosts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "api.sqlite3"
    client = TestClient(create_app(settings=_settings(database_path), connector_registrations=[]))
    connector_id = _create(client)
    document = _document()

    response = _upload(
        client,
        connector_id,
        json.dumps(document).encode(),
        approved_hosts=("api.example.com", "cdn.example.com"),
    )

    assert response.status_code == 201
    assert response.json()["approved_hosts"] == ["api.example.com", "cdn.example.com"]
    assert response.json()["operation_ids"] == ["listItems"]
    assert response.json()["selected_server_url"] == "https://api.example.com"

    recreated = TestClient(
        create_app(settings=_settings(database_path), connector_registrations=[])
    )
    assert _has_current_catalog(recreated, connector_id)


def test_file_import_normalizes_deduplicates_and_ignores_blank_approved_hosts(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(
        client,
        connector_id,
        json.dumps(_document()).encode(),
        approved_hosts=("  API.EXAMPLE.COM  ", "api.example.com", " ", "CDN.EXAMPLE.COM", ""),
    )

    assert response.status_code == 201
    assert response.json()["approved_hosts"] == ["api.example.com", "cdn.example.com"]


def test_file_import_rejects_all_blank_approved_hosts(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(
        client,
        connector_id,
        json.dumps(_document()).encode(),
        approved_hosts=("", "   "),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "Approved hosts must contain exact hostnames"


def test_file_import_exposes_operations_after_application_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "api.sqlite3"
    client = TestClient(create_app(settings=_settings(database_path), connector_registrations=[]))
    connector_id = _create(client)

    response = _upload(client, connector_id, json.dumps(_document()).encode())

    assert response.status_code == 201
    recreated = TestClient(
        create_app(settings=_settings(database_path), connector_registrations=[])
    )
    tools = recreated.get(f"/admin/connectors/openapi/{connector_id}/tools")
    assert tools.status_code == 200
    assert tools.json()["tools"] == [
        {
            "operation_id": "listItems",
            "method": "GET",
            "path": "/items",
            "summary": "",
            "description": "",
            "activation_status": "disabled",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "output_schema_status": "absent",
        }
    ]


def test_tool_catalog_exposes_flattened_operation_parameters_and_request_body(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)
    document = _document()
    operation = document["paths"]["/items"]["get"]
    operation["parameters"] = [
        {
            "name": "body",
            "in": "query",
            "required": True,
            "description": "Query body selector",
            "schema": {"type": "string"},
        }
    ]
    operation["requestBody"] = {
        "required": True,
        "description": "Item payload",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            }
        },
    }

    assert _upload(client, connector_id, json.dumps(document).encode()).status_code == 201
    parameters = client.get(f"/admin/connectors/openapi/{connector_id}/tools").json()["tools"][0][
        "parameters"
    ]

    assert parameters == {
        "type": "object",
        "properties": {
            "body": {"type": "string", "description": "Query body selector"},
            "requestBody": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": True,
                "description": "Item payload",
            },
        },
        "required": ["body", "requestBody"],
    }


def test_file_import_persists_catalog_from_uploaded_document(tmp_path: Path) -> None:
    database_path = tmp_path / "api.sqlite3"
    client = TestClient(create_app(settings=_settings(database_path), connector_registrations=[]))
    connector_id = _create(client)
    document = _document()
    document["info"]["description"] = "upload-body-token-canary"

    assert _upload(client, connector_id, json.dumps(document).encode()).status_code == 201
    assert _has_current_catalog(client, connector_id)


def test_file_import_accepts_case_insensitive_json_extension(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(client, connector_id, json.dumps(_document()).encode(), filename="SPEC.JSON")

    assert response.status_code == 201


@pytest.mark.parametrize("filename", ["", "spec.yaml", "spec.json.txt"])
def test_file_import_rejects_invalid_filename_without_catalog(
    tmp_path: Path, filename: str
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(client, connector_id, json.dumps(_document()).encode(), filename=filename)

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "openapi_import_invalid_filename"
    assert not _has_current_catalog(client, connector_id)


@pytest.mark.parametrize("media_type", ["text/yaml", "application/octet-stream"])
def test_file_import_rejects_wrong_media_type_without_catalog(
    tmp_path: Path, media_type: str
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(
        client, connector_id, json.dumps(_document()).encode(), media_type=media_type
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "openapi_import_unsupported_media_type"
    assert not _has_current_catalog(client, connector_id)


def test_file_import_accepts_exact_byte_limit_and_rejects_one_byte_over(tmp_path: Path) -> None:
    content = json.dumps(_document()).encode()
    client = TestClient(
        create_app(
            settings=_settings(tmp_path / "api.sqlite3", len(content)), connector_registrations=[]
        )
    )
    connector_id = _create(client)

    exact = _upload(client, connector_id, content)
    over = _upload(client, connector_id, content + b" ")

    assert exact.status_code == 201
    assert over.status_code == 413
    assert over.json() == {
        "detail": {"code": "openapi_import_too_large", "max_bytes": len(content)}
    }
    assert _has_current_catalog(client, connector_id)


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b'{"openapi":', "openapi_import_malformed_json"),
        (b"{} true", "openapi_import_trailing_content"),
        (b"[]", "openapi_import_json_object_required"),
        (b'"value"', "openapi_import_json_object_required"),
        (b"\xff", "openapi_import_invalid_utf8"),
    ],
)
def test_file_import_rejects_invalid_json_without_catalog(
    tmp_path: Path, content: bytes, code: str
) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(client, connector_id, content)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code
    assert not _has_current_catalog(client, connector_id)


def test_file_import_maps_semantic_validation_issues_without_catalog(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)

    response = _upload(client, connector_id, b'{"openapi":"2.0"}')

    assert response.status_code == 422
    assert response.json()["detail"]["issues"]
    assert not _has_current_catalog(client, connector_id)


def test_file_import_unknown_connector_returns_404(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )

    response = _upload(client, "missing", json.dumps(_document()).encode())

    assert response.status_code == 404


def test_tool_catalog_selects_first_declared_json_success_output_schema(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)
    document = _document()
    operation = document["paths"]["/items"]["get"]
    operation["responses"] = {
        "200": {"description": "schema-less", "content": {"application/json": {}}},
        "202": {
            "description": "accepted",
            "content": {
                "application/problem+json": {"schema": {"type": "string"}},
                "application/json": {"schema": {}},
            },
        },
        "default": {
            "description": "fallback",
            "content": {"application/json": {"schema": {"type": "boolean"}}},
        },
    }

    assert _upload(client, connector_id, json.dumps(document).encode()).status_code == 201
    tool = client.get(f"/admin/connectors/openapi/{connector_id}/tools").json()["tools"][0]

    assert tool["output_schema_status"] == "present"
    assert tool["output_schema"] == {}


def test_tool_catalog_uses_declared_json_default_output_schema(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings=_settings(tmp_path / "api.sqlite3"), connector_registrations=[])
    )
    connector_id = _create(client)
    document = _document()
    operation = document["paths"]["/items"]["get"]
    operation["responses"] = {
        "404": {
            "description": "error",
            "content": {"application/json": {"schema": {"type": "string"}}},
        },
        "default": {
            "description": "fallback",
            "content": {"application/vnd.example+json": {"schema": {"type": "boolean"}}},
        },
    }

    assert _upload(client, connector_id, json.dumps(document).encode()).status_code == 201
    tool = client.get(f"/admin/connectors/openapi/{connector_id}/tools").json()["tools"][0]

    assert tool["output_schema_status"] == "present"
    assert tool["output_schema"] == {"type": "boolean"}
