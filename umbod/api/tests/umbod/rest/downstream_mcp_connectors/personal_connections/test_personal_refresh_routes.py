import pytest

from tests.umbod.rest.downstream_mcp_connectors.personal_connections.test_personal_connection_routes import PersonalApi, personal_api
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import PersonalRefreshChanged, PersonalRefreshConflict, PersonalRefreshReconnectRequired, PersonalRefreshUnsupported
from umbod.rest.connectors.downstream_mcp.personal_connections.refresh_dependencies import get_personal_refresh_service
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_dependencies import require_personal_oauth

__all__ = ["personal_api"]


@pytest.fixture(autouse=True)
def enabled_refresh(personal_api: PersonalApi) -> None:
    personal_api.personal_app.dependency_overrides[require_personal_oauth] = lambda: None


class ObservedRefreshService:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[str] = []

    async def refresh(self, connector_id: str) -> None:
        self.calls.append(connector_id)
        failures = {"unsupported": PersonalRefreshUnsupported, "conflict": PersonalRefreshConflict, "changed": PersonalRefreshChanged, "reconnect_required": PersonalRefreshReconnectRequired, "unavailable": RuntimeError}
        if self.result in failures:
            raise failures[self.result]("secret-refresh-token https://issuer.example/token")


@pytest.mark.parametrize("body", [b"", b"null", b"[]", b"false", b"{", b'{"refresh_token":"secret"}', b" " * 1025 + b"{}"])
def test_refresh_requires_bounded_strict_empty_json(personal_api: PersonalApi, body: bytes) -> None:
    service = ObservedRefreshService("success")
    personal_api.personal_app.dependency_overrides[get_personal_refresh_service] = lambda: service
    response = personal_api.client.post(personal_api.url + "/authorization/refresh", headers=personal_api.headers("alice"), content=body)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "personal_refresh_invalid_request"}}
    assert response.headers["cache-control"] == "no-store"
    assert not service.calls


@pytest.mark.parametrize("result,expected", [("success", 200), ("unsupported", 409), ("conflict", 409), ("changed", 409), ("reconnect_required", 409), ("unavailable", 503)])
def test_refresh_returns_fixed_secret_free_no_store_contract(personal_api: PersonalApi, result: str, expected: int) -> None:
    service = ObservedRefreshService(result)
    personal_api.personal_app.dependency_overrides[get_personal_refresh_service] = lambda: service
    response = personal_api.client.post(personal_api.url + "/authorization/refresh", headers=personal_api.headers("alice"), json={})
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"
    assert "secret-refresh-token" not in response.text
    assert "issuer.example" not in response.text
    assert service.calls == [personal_api.connector_id]
    expected_body = {"status": "refreshed", "discovery_required": True} if result == "success" else {"detail": {"code": "personal_refresh_" + result}}
    assert response.json() == expected_body


@pytest.mark.parametrize("headers,expected", [({}, 401), ({"X-Access": "invalid"}, 401), ({"X-Access": "unmapped"}, 403)])
def test_refresh_preserves_authentication_and_canonical_identity_gate(personal_api: PersonalApi, headers: dict[str, str], expected: int) -> None:
    response = personal_api.client.post(personal_api.url + "/authorization/refresh", headers=headers, json={})
    assert response.status_code == expected


@pytest.mark.parametrize("withdrawal", ["publication", "grant"])
def test_refresh_preserves_hidden_eligibility_before_any_provider_contact(personal_api: PersonalApi, withdrawal: str) -> None:
    if withdrawal == "publication":
        personal_api.client.delete(f"/api/admin/connectors/mcp/{personal_api.connector_id}/publication", headers=personal_api.admin_headers).raise_for_status()
    else:
        personal_api.client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=personal_api.admin_headers, json={"connectors": [{"connector_id": personal_api.connector_id, "permission_status": "disabled"}]}).raise_for_status()
    response = personal_api.client.post(personal_api.url + "/authorization/refresh", headers=personal_api.headers("alice"), json={})
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "personal_connector_not_found"}}
