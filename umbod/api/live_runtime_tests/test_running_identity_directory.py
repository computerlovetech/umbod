import time

import httpx
import jwt
import pytest

from conftest import RuntimeEndpoints


def test_development_identity_observation_is_skipped_without_mutation(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "none":
        pytest.skip("Requires the runner's development-authentication phase")
    headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30
    ) as client:
        before = client.get("/api/admin/identity-directory/users")
        assert before.status_code == 200, before.text
        groups = client.get("/api/admin/identity-directory/groups")
        assert groups.status_code == 200, groups.text
        assert client.post("/api/me/identity-observations").status_code == 204
        assert client.get("/api/admin/identity-directory/users").json() == before.json()
        assert (
            client.get("/api/admin/identity-directory/groups").json() == groups.json()
        )


def test_signed_identity_observation_and_admin_directory(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30
    ) as client:
        registered = client.get("/api/admin/groups")
        assert registered.status_code == 200, registered.text
        assert client.post("/api/me/identity-observations").status_code == 204
        deadline = time.monotonic() + 15
        while True:
            users = client.get("/api/admin/identity-directory/users")
            assert users.status_code == 200, users.text
            if users.json()["users"] or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        assert users.json()["users"]
        first = users.json()["users"][0]
        assert first["issuer"] == users.json()["issuer"]
        assert first["user_id"]
        assert client.post("/api/me/identity-observations").status_code == 204
        repeated = client.get("/api/admin/identity-directory/users").json()["users"]
        assert repeated[0]["user_id"] == first["user_id"]
        groups = client.get("/api/admin/identity-directory/groups")
        assert groups.status_code == 200, groups.text
        assert set(groups.json()) == {"issuer", "claim", "groups", "has_more"}
        assert groups.json()["groups"]
        assert client.get("/api/admin/groups").json() == registered.json()
        assert (
            client.post(
                "/api/me/identity-observations", json={"groups": ["injected"]}
            ).status_code
            == 422
        )
        assert (
            client.get("/api/admin/identity-directory/groups?limit=101").status_code
            == 422
        )
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as anonymous:
        assert anonymous.post("/api/me/identity-observations").status_code == 401
        assert anonymous.get("/api/admin/identity-directory/users").status_code == 401
