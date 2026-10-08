from uuid import uuid4

import httpx

from conftest import RuntimeEndpoints


def test_canonical_api_identity_succeeds_and_legacy_api_is_not_found(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        public_response = client.get("/api/admin/users")
        legacy_response = client.get("/admin/users", follow_redirects=False)
    assert public_response.status_code == 200
    assert public_response.json()["id"]
    assert legacy_response.status_code == 404
    assert "location" not in legacy_response.headers


def test_native_bearer_client_can_read_public_api_contract(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        response = client.get("/api/admin/openapi.json")
    assert response.status_code == 200
    assert "/connectors/openapi" in response.json()["paths"]


def test_native_bearer_client_can_register_permission_group(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = f"native-runtime-{uuid4()}"
    path = f"/api/admin/mcp-permissions/groups/{group_id}"
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        try:
            response = client.post(path)
            assert response.status_code == 200
            assert client.get(path).status_code == 200
        finally:
            client.delete(path)


def test_native_client_can_complete_openapi_setup_in_one_request(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    request = {
        "display_name": f"Native setup {uuid4()}",
        "tool_name_prefix": "native_runtime",
        "capability_description": "Runtime verification of client-independent setup",
        "document": {
            "openapi": "3.0.3",
            "info": {"title": "Runtime API", "version": "1.0"},
            "servers": [{"url": "https://runtime.invalid"}],
            "paths": {
                "/status": {
                    "get": {
                        "operationId": "status",
                        "responses": {"200": {"description": "Status"}},
                    }
                }
            },
        },
        "approved_hosts": ["runtime.invalid"],
        "authentication_type": "none",
        "bearer_token": "",
    }
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        response = client.post("/api/admin/connectors/openapi/setup", json=request)
        assert response.status_code == 201
        connector_id = response.json()["connector_id"]
        path = f"/api/admin/connectors/openapi/{connector_id}"
        try:
            tools = client.get(f"{path}/tools")
            assert tools.status_code == 200
            assert [tool["operation_id"] for tool in tools.json()["tools"]] == ["status"]
        finally:
            client.delete(path)


def test_cookie_mutation_without_browser_csrf_header_is_rejected(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    group_id = f"csrf-runtime-{uuid4()}"
    headers = {
        "Authorization": f"Bearer {runtime_endpoints.bearer_token}",
        "Cookie": "web-session=runtime-test",
        "Origin": "https://untrusted.invalid",
    }
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers=headers) as client:
        response = client.post(f"/api/admin/mcp-permissions/groups/{group_id}")
    assert response.status_code == 403
