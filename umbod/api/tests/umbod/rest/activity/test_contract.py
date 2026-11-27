import pytest

from .conftest import BASE, DETAIL, SESSIONS, ActivityApi

@pytest.mark.parametrize(("subject", "detail"), [
    ("alice", DETAIL),
    ("bob", SESSIONS + "/codex/bob-private"),
])
def test_activity_responses_use_same_verified_identity_key_as_profile(
    api: ActivityApi, subject: str, detail: str,
) -> None:
    headers = api.headers(subject)
    profile = api.client.get("/api/me/profile", headers=headers)
    assert profile.status_code == 200
    other_profile = api.client.get("/api/me/profile", headers=api.headers("bob" if subject == "alice" else "alice"))
    assert other_profile.status_code == 200
    identity_key = profile.json()["identity_key"]
    assert identity_key and identity_key != other_profile.json()["identity_key"]

    for path in (BASE, SESSIONS, detail):
        response = api.client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json()["identity_key"] == identity_key


def test_personal_openapi_omits_retired_usage_route(api: ActivityApi) -> None:
    response = api.client.get("/api/me/openapi.json", headers=api.headers("alice"))

    assert response.status_code == 200
    assert "/usage" not in response.json()["paths"]


def test_personal_openapi_requires_activity_identity(api: ActivityApi) -> None:
    response = api.client.get("/api/me/openapi.json", headers=api.headers("alice"))

    assert response.status_code == 200
    document = response.json()
    for path, statuses in (
        ("/activity", ("200", "503")),
        ("/activity/sessions", ("200",)),
        ("/activity/sessions/{source}/{session_id}", ("200",)),
    ):
        operation = document["paths"][path]["get"]
        for status in statuses:
            ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
            schema = document["components"]["schemas"][ref.rsplit("/", 1)[-1]]
            assert "identity_key" in schema["required"]
            assert schema["properties"]["identity_key"]["type"] == "string"
