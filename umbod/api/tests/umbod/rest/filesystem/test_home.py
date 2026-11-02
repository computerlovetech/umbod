from umbod.rest.authentication.deps import get_caller_context

from .conftest import FilesystemHttp
from .test_http_contract import BASE


def test_home_post_is_idempotent_private_and_needs_no_root_grant(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    headers = {"Authorization": "Bearer outsider"}
    assert client.get(BASE + "/browse", headers=headers).status_code == 403
    first = client.post(BASE + "/home", headers=headers)
    repeated = client.post(BASE + "/home", headers=headers)
    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json()
    assert first.headers["cache-control"] == "no-store"
    node = first.json()
    assert node["permissions"] == {
        "can_discover": True, "can_read": True, "can_write": True, "can_delete": False, "can_share": True,
    }
    assert node["visible_to"] == {
        "type": "available", "scope": "direct_node_policy", "owner": {
            "type": "user", "issuer": "issuer", "id": "outsider",
        }, "grants": [], "group_members_expanded": False,
    }
    assert client.get(BASE + "/home", headers=headers).status_code == 405
    assert client.get(f"{BASE}/nodes/{node['id']}", headers=headers).json() == node
    assert client.get(f"{BASE}/nodes/{node['id']}").status_code == 403
    browse = client.get(BASE + "/browse", params={"node_id": node["id"]}, headers=headers).json()
    assert browse["node"] == node
    assert browse["entries"] == []


def test_home_denies_unverified_or_unauthenticated_callers(filesystem_http: FilesystemHttp) -> None:
    del filesystem_http.app.dependency_overrides[get_caller_context]
    response = filesystem_http.client.post(BASE + "/home")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert filesystem_http.client.post(BASE + "/home", headers={"Authorization": ""}).status_code == 401
