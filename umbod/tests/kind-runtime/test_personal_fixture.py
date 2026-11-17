import base64
import hashlib
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import pytest_asyncio

import personal_fixture


@pytest_asyncio.fixture
async def provider(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    for name in ("modes", "registered_clients", "codes", "tokens", "refresh_tokens", "refresh_release"):
        monkeypatch.setattr(personal_fixture, name, {})
    monkeypatch.setattr(personal_fixture, "counters", dict.fromkeys(personal_fixture.counters, 0))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=personal_fixture.application), base_url=personal_fixture.ISSUER,
    ) as client:
        yield client


def registration(method: str) -> dict[str, Any]:
    return {
        "redirect_uris": ["https://umbod-runtime.kind.invalid/api/oauth/downstream-mcp/callback"],
        "application_type": "web", "token_endpoint_auth_method": method,
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], "scope": "read",
    }


def credentials(client: dict[str, Any], method: str) -> dict[str, Any]:
    if method == "client_secret_basic":
        encoded = base64.b64encode((client["client_id"] + ":" + client["client_secret"]).encode()).decode()
        return {"headers": {"Authorization": "Basic " + encoded}}
    return {"data": {"client_id": client["client_id"], "client_secret": client["client_secret"]}}


async def token_request(
    provider: httpx.AsyncClient, grant: dict[str, str], authentication: dict[str, Any],
) -> httpx.Response:
    return await provider.post("/token", data={**grant, **authentication.get("data", {})}, headers=authentication.get("headers", {}))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,methods", [
    ("normal", ["none", "client_secret_basic"]),
    ("confidential_only", ["client_secret_post", "client_secret_basic"]),
    ("confidential_basic", ["client_secret_basic"]),
    ("confidential_post", ["client_secret_post"]),
])
async def test_fixture_metadata_and_registration_honor_controlled_methods(
    provider: httpx.AsyncClient, mode: str, methods: list[str],
) -> None:
    await provider.post("/control", json={"owner": "metadata", "mode": mode})
    metadata = await provider.get("/.well-known/oauth-authorization-server")
    assert metadata.json()["token_endpoint_auth_methods_supported"] == methods
    for method in methods:
        first = await provider.post("/register", json=registration(method))
        second = await provider.post("/register", json=registration(method))
        assert first.status_code == second.status_code == 201
        assert first.json()["client_id"] != second.json()["client_id"]
        assert first.json()["token_endpoint_auth_method"] == method
        if method != "none":
            assert first.json()["client_secret"].startswith("kind-personal-dcr-secret-")
            assert first.json()["client_secret_expires_at"] == 0
            assert first.json()["client_secret"] != second.json()["client_secret"]
        else:
            assert "client_secret" not in first.json()
    counters = await provider.get("/control")
    assert counters.json()["registrations"] == 2 * len(methods)
    assert all(isinstance(value, int) for value in counters.json().values())
    assert "kind-personal-dcr-secret-" not in counters.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("token_endpoint_auth_method", "none"),
    ("redirect_uris", ["https://attacker.invalid/callback"]),
    ("application_type", "native"),
    ("grant_types", ["client_credentials"]),
    ("response_types", ["token"]),
    ("scope", "write"),
])
async def test_fixture_rejects_unsupported_registration_metadata(
    provider: httpx.AsyncClient, field: str, value: Any,
) -> None:
    await provider.post("/control", json={"owner": "metadata", "mode": "confidential_only"})
    response = await provider.post("/register", json={**registration("client_secret_basic"), field: value})
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_client_metadata"}


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
async def test_fixture_requires_registered_credentials_for_exchange_and_refresh(
    provider: httpx.AsyncClient, method: str,
) -> None:
    await provider.post("/control", json={"owner": "metadata", "mode": "confidential_only"})
    registered = (await provider.post("/register", json=registration(method))).json()
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    parameters = {
        "client_id": registered["client_id"], "redirect_uri": registration(method)["redirect_uris"][0],
        "response_type": "code", "scope": "read", "resource": personal_fixture.RESOURCE,
        "state": "fixture-test-state", "code_challenge_method": "S256", "code_challenge": challenge,
        "owner": "alice",
    }
    consent = await provider.get("/authorize?" + urlencode(parameters))
    assert consent.status_code == 302
    callback = parse_qs(urlsplit(consent.headers["location"]).query)
    assert callback["state"] == [parameters["state"]]
    assert callback["iss"] == [personal_fixture.ISSUER]
    grant = {
        "grant_type": "authorization_code", "code": callback["code"][0], "code_verifier": verifier,
        "redirect_uri": parameters["redirect_uri"], "resource": personal_fixture.RESOURCE,
    }
    other_method = "client_secret_post" if method == "client_secret_basic" else "client_secret_basic"
    invalid_authentication = [
        {"data": {"client_id": registered["client_id"]}},
        credentials({**registered, "client_secret": "incorrect"}, method),
        credentials(registered, other_method),
        {"headers": {"Authorization": "Basic malformed!"}},
    ]
    for authentication in invalid_authentication:
        rejected = await token_request(provider, grant, authentication)
        assert rejected.status_code == 401
        assert rejected.json() == {"error": "invalid_client"}
    exchanged = await token_request(provider, grant, credentials(registered, method))
    assert exchanged.status_code == 200
    refresh_grant = {"grant_type": "refresh_token", "refresh_token": exchanged.json()["refresh_token"], "resource": personal_fixture.RESOURCE}
    for authentication in invalid_authentication:
        rejected = await token_request(provider, refresh_grant, authentication)
        assert rejected.status_code == 401
        assert rejected.json() == {"error": "invalid_client"}
    other_client = (await provider.post("/register", json=registration(method))).json()
    wrong_binding = await token_request(provider, refresh_grant, credentials(other_client, method))
    assert wrong_binding.status_code == 400
    assert wrong_binding.json() == {"error": "invalid_grant"}
    refreshed = await token_request(provider, refresh_grant, credentials(registered, method))
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != refresh_grant["refresh_token"]
    replay = await token_request(provider, refresh_grant, credentials(registered, method))
    assert replay.status_code == 400
    assert replay.json() == {"error": "invalid_grant"}
    assert (await provider.get("/control")).json()["registrations"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("client_id", "unknown-client"),
    ("redirect_uri", "https://attacker.invalid/callback"),
    ("response_type", "token"),
    ("scope", "write"),
    ("resource", "https://attacker.invalid/mcp"),
    ("state", ""),
    ("code_challenge", ""),
    ("code_challenge_method", "plain"),
])
async def test_fixture_rejects_invalid_authorization_requests(
    provider: httpx.AsyncClient, field: str, value: str,
) -> None:
    parameters = {
        "client_id": "kind-personal-client", "redirect_uri": registration("none")["redirect_uris"][0],
        "response_type": "code", "scope": "read", "resource": personal_fixture.RESOURCE,
        "state": "fixture-test-state", "code_challenge_method": "S256", "code_challenge": "c" * 43,
        "owner": "alice",
    }
    accepted = await provider.get("/authorize?" + urlencode(parameters))
    assert accepted.status_code == 302
    rejected = await provider.get("/authorize?" + urlencode({**parameters, field: value}))
    assert rejected.status_code == 400
    assert rejected.json() == {"error": "invalid_request"}
