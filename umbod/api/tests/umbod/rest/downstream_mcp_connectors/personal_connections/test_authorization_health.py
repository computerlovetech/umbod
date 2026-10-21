from datetime import UTC, datetime, timedelta

import pytest

from tests.umbod.rest.downstream_mcp_connectors.personal_connections.test_personal_connection_routes import PersonalApi, personal_api
from umbod.core.connectors.downstream_mcp.personal_connections.health_models import LocallyAuthorized, PersonalAuthorizationHealth, PersonalAuthorizationHealthQuery
from umbod.rest.connectors.downstream_mcp.personal_connections.authorization import get_personal_authorization_health

__all__ = ["personal_api"]


def test_health_get_is_safe_no_store_and_does_not_change_selection(personal_api: PersonalApi) -> None:
    headers = personal_api.headers("alice")
    before = personal_api.client.get(personal_api.url, headers=headers).json()
    result = personal_api.client.get(personal_api.url + "/authorization", headers=headers)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == {"state": "not_authorized"}
    assert personal_api.client.get(personal_api.url, headers=headers).json() == before


@pytest.mark.parametrize("headers,expected", [({}, 401), ({"X-Access": "invalid"}, 401), ({"X-Access": "unmapped"}, 403)])
def test_health_preserves_verified_identity_gate(personal_api: PersonalApi, headers: dict[str, str], expected: int) -> None:
    assert personal_api.client.get(personal_api.url + "/authorization", headers=headers).status_code == expected


@pytest.mark.parametrize("withdrawal", ["publication", "grant"])
def test_health_uses_same_non_enumerating_eligibility_as_detail(personal_api: PersonalApi, withdrawal: str) -> None:
    headers = personal_api.headers("alice")
    personal_api.client.put(personal_api.url + "/enablement", headers=headers, json={"enabled": True}).raise_for_status()
    if withdrawal == "publication":
        personal_api.client.delete(f"/api/admin/connectors/mcp/{personal_api.connector_id}/publication", headers=personal_api.admin_headers).raise_for_status()
    else:
        personal_api.client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=personal_api.admin_headers, json={"connectors": [{"connector_id": personal_api.connector_id, "permission_status": "disabled"}]}).raise_for_status()
    result = personal_api.client.get(personal_api.url + "/authorization", headers=headers)
    assert result.status_code == 404
    assert result.json() == personal_api.client.get(personal_api.url, headers=headers).json()
    assert personal_api.client.delete(personal_api.url + "/authorization", headers=headers).status_code == 204


class ObservedHealthStore:
    def __init__(self, failing: bool) -> None:
        self.failing = failing
        self.queries: list[PersonalAuthorizationHealthQuery] = []

    async def get(self, query: PersonalAuthorizationHealthQuery) -> PersonalAuthorizationHealth:
        self.queries.append(query)
        if self.failing:
            raise RuntimeError("secret-token https://private-provider.example")
        return LocallyAuthorized(expires_at=datetime.now(UTC) + timedelta(hours=1), refresh_supported=False)


@pytest.mark.parametrize("failing", [True, False])
def test_health_is_owner_scoped_and_operational_failures_are_sanitized(personal_api: PersonalApi, failing: bool) -> None:
    store = ObservedHealthStore(failing)
    personal_api.personal_app.dependency_overrides[get_personal_authorization_health] = lambda: store
    result = personal_api.client.get(personal_api.url + "/authorization?owner=bob", headers=personal_api.headers("alice"))
    assert result.status_code == (503 if failing else 200)
    assert result.headers["cache-control"] == "no-store"
    assert store.queries[0].key.principal.subject == "alice"
    assert "secret-token" not in result.text
    assert "private-provider" not in result.text
    if not failing:
        assert result.json()["state"] == "authorized"
        assert personal_api.client.get(personal_api.url, headers=personal_api.headers("alice")).json()["enabled"] is False
