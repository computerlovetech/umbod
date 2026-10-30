from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.filesystem.models import AccessGrant, Principal, PrincipalType
from umbod.core.filesystem.stores.access_control import DatabaseAccessControl
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


def group_record(group_id: str) -> dict[str, object]:
    return {"group_id": group_id, "label": group_id, "description": "", "revision": 1}


@pytest.fixture(autouse=True)
def connector_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "availability.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = APISettings(
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        connector_store={
            "type": "sqlite",
            "sqlite_path": str(tmp_path / "groups.sqlite3"),
        },
        rest={"metrics_enabled": False},
    )
    with TestClient(
        create_app(settings=settings, connector_registrations=[])
    ) as client:
        yield client


def test_shared_registration_is_exact_idempotent_and_legacy_visible(
    client: TestClient,
) -> None:
    assert client.get("/api/admin/groups").json() == {"groups": []}
    for group_id in (" Team ", "team", "Team", " Team "):
        response = client.post("/api/admin/groups", json={"group_id": group_id})
        assert response.status_code == 204
        assert response.content == b""
    expected = {
        "groups": [group_record(value) for value in (" Team ", "Team", "team")]
    }
    assert client.get("/api/admin/groups").json() == expected
    assert client.get("/api/admin/mcp-permissions/groups").json() == {
        "groups": [{"group_id": value} for value in (" Team ", "Team", "team")]
    }
    assert (
        client.get("/api/admin/mcp-permissions/groups/team").json()["connector_ids"]
        == []
    )


def test_legacy_registration_and_deletion_use_shared_catalogue(
    client: TestClient,
) -> None:
    response = client.post("/api/admin/mcp-permissions/groups/legacy")
    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert client.get("/api/admin/groups").json() == {
        "groups": [group_record("legacy")]
    }
    assert client.delete("/api/admin/mcp-permissions/groups/legacy").status_code == 200
    assert client.get("/api/admin/groups").json() == {"groups": []}
    assert client.delete("/api/admin/groups/unknown").status_code == 204


@pytest.mark.parametrize("group_id", [".", "..", "a/../b", " spaced/group "])
def test_body_deletion_and_query_permissions_preserve_exact_identifiers(
    client: TestClient, group_id: str
) -> None:
    assert (
        client.post("/api/admin/groups", json={"group_id": group_id}).status_code == 204
    )
    detail = client.get(
        "/api/admin/mcp-permissions/group-permissions", params={"group_id": group_id}
    )
    assert detail.status_code == 200
    assert detail.json() == {
        "group_id": group_id,
        "connector_ids": [],
        "capabilities": [],
    }
    update = client.put(
        "/api/admin/mcp-permissions/group-permissions",
        params={"group_id": group_id},
        json={
            "connectors": [{"connector_id": "absent", "permission_status": "disabled"}]
        },
    )
    assert update.status_code == 200
    assert update.json()["group_id"] == group_id
    assert client.get("/api/admin/groups").json() == {
        "groups": [group_record(group_id)]
    }
    assert (
        client.request(
            "DELETE", "/api/admin/groups", json={"group_id": group_id}
        ).status_code
        == 204
    )
    assert client.get("/api/admin/groups").json() == {"groups": []}


@pytest.mark.asyncio
async def test_observed_empty_identifier_supports_query_reads_and_body_deletion(
    client: TestClient, tmp_path: Path
) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "groups.sqlite3")
    policies = DatabaseAccessControl(runtime.database)
    grant = AccessGrant(
        node_id=uuid4(),
        principal=Principal(type=PrincipalType.GROUP, issuer="", id=""),
        permissions=set(),
        recursive=False,
    )
    try:
        await policies.add_grant(grant)
        assert client.get("/api/admin/groups").json() == {"groups": [group_record("")]}
        detail = client.get(
            "/api/admin/mcp-permissions/group-permissions", params={"group_id": ""}
        )
        assert detail.status_code == 200
        assert detail.json() == {
            "group_id": "",
            "connector_ids": [],
            "capabilities": [],
        }
        assert (
            client.request(
                "DELETE", "/api/admin/groups", json={"group_id": ""}
            ).status_code
            == 409
        )
        await policies.remove_grant(grant.node_id, grant.principal)
        assert (
            client.request(
                "DELETE", "/api/admin/groups", json={"group_id": ""}
            ).status_code
            == 204
        )
        assert client.get("/api/admin/groups").json() == {"groups": []}
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("body_route", [False, True])
def test_metadata_roundtrip_conflict_and_missing(client: TestClient, body_route: bool) -> None:
    group_id = "provider/a/../team" if body_route else "provider/team"
    assert client.post("/api/admin/groups", json={"group_id": group_id, "label": "Team", "description": "Original"}).status_code == 204
    payload = {"label": "Edited", "description": "Saved", "expected_revision": 1}
    path = f"/api/admin/groups/{group_id}"
    if body_route:
        path = "/api/admin/groups"
        payload["group_id"] = group_id
    response = client.put(path, json=payload)
    assert response.status_code == 200
    expected = {"group_id": group_id, "label": "Edited", "description": "Saved", "revision": 2}
    assert response.json() == expected
    assert client.put(path, json=payload).status_code == 409
    client.post("/api/admin/groups", json={"group_id": group_id})
    assert expected in client.get("/api/admin/groups").json()["groups"]
    assert client.put("/api/admin/groups/missing", json={"label": "Missing", "description": "", "expected_revision": 1}).status_code == 404


@pytest.mark.parametrize("payload", [
    {"label": ""}, {"label": "  "}, {"label": "x" * 201},
    {"description": "x" * 2001}, {"expected_revision": 0},
    {"expected_revision": True}, {"expected_revision": "1"},
    {"group_id": "renamed"}, {"issuer": "authority"}, {"permissions": []},
])
def test_metadata_update_rejects_invalid_or_authority_fields(client: TestClient, payload: dict[str, object]) -> None:
    request = {"label": "Team", "description": "", "expected_revision": 1, **payload}
    assert client.put("/api/admin/groups/team", json=request).status_code == 422


@pytest.mark.parametrize("payload", [
    {"label": ""}, {"label": " "}, {"label": "x" * 201}, {"label": None},
    {"description": "x" * 2001}, {"revision": 1}, {"permissions": []},
])
def test_registration_rejects_invalid_metadata(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/api/admin/groups", json={"group_id": "team", **payload}).status_code == 422


def test_unknown_permission_reads_do_not_register_groups(client: TestClient) -> None:
    response = client.get("/api/admin/mcp-permissions/groups/unknown")
    assert response.status_code == 200
    assert response.json()["connector_ids"] == []
    assert response.json()["capabilities"] == []
    assert client.get("/api/admin/groups").json() == {"groups": []}


def test_path_group_identifier_can_contain_slashes(client: TestClient) -> None:
    group_id = " provider/team "
    assert (
        client.post("/api/admin/groups", json={"group_id": group_id}).status_code == 204
    )
    assert (
        client.delete(f"/api/admin/groups/{quote(group_id, safe='/')}").status_code
        == 204
    )
    assert client.get("/api/admin/groups").json() == {"groups": []}


@pytest.mark.parametrize(
    "payload",
    [
        {"group_id": ""},
        {"group_id": " \n\t"},
        {"group_id": 12},
        {},
        {"group_id": "team", "issuer": "issuer"},
    ],
)
def test_registration_validates_json_body(
    client: TestClient, payload: dict[str, object]
) -> None:
    assert client.post("/api/admin/groups", json=payload).status_code == 422
    assert client.get("/api/admin/groups").json() == {"groups": []}


def test_filesystem_reference_blocks_both_delete_routes(client: TestClient) -> None:
    state = client.get("/api/admin/filesystem/root-access").json()
    response = client.put(
        "/api/admin/filesystem/root-access",
        json={
            "expected_revision": state["revision"],
            "groups": [
                {
                    "group_id": "filesystem-only",
                    "permissions": ["discover"],
                }
            ],
        },
    )
    assert response.status_code == 200
    assert client.get("/api/admin/groups").json() == {
        "groups": [group_record("filesystem-only")]
    }
    assert (
        client.request(
            "DELETE", "/api/admin/groups", json={"group_id": "filesystem-only"}
        ).status_code
        == 409
    )
    assert client.delete("/api/admin/groups/filesystem-only").status_code == 409
    assert (
        client.delete("/api/admin/mcp-permissions/groups/filesystem-only").status_code
        == 409
    )


def test_stale_root_save_does_not_register_rejected_group(client: TestClient) -> None:
    state = client.get("/api/admin/filesystem/root-access").json()
    assert (
        client.put(
            "/api/admin/filesystem/root-access",
            json={"expected_revision": state["revision"], "groups": []},
        ).status_code
        == 200
    )
    response = client.put(
        "/api/admin/filesystem/root-access",
        json={
            "expected_revision": state["revision"],
            "groups": [
                {
                    "group_id": "stale-only",
                    "permissions": ["discover"],
                }
            ],
        },
    )
    assert response.status_code == 409
    assert client.get("/api/admin/groups").json() == {"groups": []}


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/admin/groups"),
        ("put", "/api/admin/groups/team"),
        ("put", "/api/admin/groups"),
        ("delete", "/api/admin/groups/team"),
        ("delete", "/api/admin/groups"),
        ("put", "/api/admin/mcp-permissions/group-permissions?group_id=."),
    ],
)
def test_cookie_mutations_require_origin_and_marker(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(
        method,
        path,
        json={"group_id": "team"} if method == "post" else None,
        headers={"Cookie": "session=value"},
    )
    assert response.status_code == 403


def test_unauthenticated_group_routes_reject_requests(tmp_path: Path) -> None:
    settings = APISettings(
        admin_authentication={
            "mode": "jwt",
            "jwks_url": "https://issuer.example/jwks",
            "membership_claim": "groups",
            "required_membership": "admin",
        },
        connector_store={
            "type": "sqlite",
            "sqlite_path": str(tmp_path / "auth.sqlite3"),
        },
        rest={"metrics_enabled": False},
    )
    with TestClient(
        create_app(settings=settings, connector_registrations=[])
    ) as client:
        assert client.get("/api/admin/groups").status_code == 401
        assert (
            client.post("/api/admin/groups", json={"group_id": "team"}).status_code
            == 401
        )
        assert client.delete("/api/admin/groups/team").status_code == 401
        assert client.put("/api/admin/groups/team", json={}).status_code == 401
        assert client.put("/api/admin/groups", json={}).status_code == 401
        assert (
            client.request(
                "DELETE", "/api/admin/groups", json={"group_id": "."}
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/admin/mcp-permissions/group-permissions", params={"group_id": "."}
            ).status_code
            == 401
        )
        assert (
            client.put(
                "/api/admin/mcp-permissions/group-permissions",
                params={"group_id": "."},
                json={
                    "connectors": [
                        {"connector_id": "absent", "permission_status": "disabled"}
                    ]
                },
            ).status_code
            == 401
        )
