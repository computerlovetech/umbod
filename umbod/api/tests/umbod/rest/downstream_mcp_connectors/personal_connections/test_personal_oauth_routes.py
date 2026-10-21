import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from umbod.config import AppConfig
from umbod.core.connectors.downstream_mcp.personal_connections.models import Authorized
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    ExchangePersonalOAuth, PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported,
    PreparePersonalOAuth, PreparedPersonalOAuth,
)
from umbod.rest.main import create_app
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_callback import (
    CALLBACK_PATH, CALLBACK_QUERY_KEY, PersonalOAuthQueryRedactionMiddleware,
)
from starlette.types import Message, Receive, Scope, Send
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_dependencies import get_personal_oauth_provider

from test_personal_connection_routes import ForbiddenProbe, UserVerifier, _create_connector
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe


class FakeOAuthProvider:
    def __init__(self) -> None:
        self.preparations: list[PreparePersonalOAuth] = []
        self.exchanges: list[ExchangePersonalOAuth] = []
        self.fail_exchange = False
        self.preparation_failures: list[Exception] = []

    async def prepare(self, command: PreparePersonalOAuth) -> PreparedPersonalOAuth:
        self.preparations.append(command)
        if self.preparation_failures:
            raise self.preparation_failures.pop()
        return PreparedPersonalOAuth(
            authorization_url=SecretStr("https://issuer.example/authorize?" + urlencode({
                "state": command.state.get_secret_value(),
            })), context=SecretStr("private-provider-context"),
        )

    async def exchange(self, command: ExchangePersonalOAuth) -> Authorized:
        self.exchanges.append(command)
        if self.fail_exchange:
            raise ValueError("secret-code secret-state private-provider-context")
        return Authorized(authorization=SecretStr("private-token"))


@dataclass(frozen=True)
class OAuthApi:
    client: TestClient
    settings: AppConfig
    provider: FakeOAuthProvider
    connector_id: str
    admin_headers: dict[str, str]
    app: FastAPI

    @property
    def url(self) -> str:
        return f"/api/me/connectors/mcp/{self.connector_id}/oauth/attempts"

    def start(self) -> dict[str, str]:
        response = self.client.post(self.url, headers={"X-Access": "alice"}, json={})
        response.raise_for_status()
        return response.json()

    def callback(self) -> str:
        return CALLBACK_PATH + "?" + urlencode({
            "state": self.provider.preparations[-1].state.get_secret_value(),
            "code": "secret-code", "iss": "https://issuer.example",
        })


@pytest.fixture
def oauth_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[OAuthApi]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "oauth.sqlite3")},
        connector_security={"configuration_secret": "test-personal-oauth-encryption-key"},
        rest={"metrics_enabled": False},
        admin_authentication={
            "mode": "jwt", "environment": "development", "required_membership": "admins",
            "membership_claim": "groups", "jwt_header_name": "X-Access",
        },
        mcp={"permission_group_claim": "groups"},
        personal_connections={"enabled": True, "oauth_enabled": True, "identity_namespace": "test:oauth-api"},
    )
    app = create_app(settings, [], user_verifier=UserVerifier())
    provider = FakeOAuthProvider()
    for route in app.routes:
        child = getattr(route, "app", None)
        if isinstance(child, FastAPI):
            child.dependency_overrides[get_personal_oauth_provider] = lambda: provider
    admin_app = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/admin")
    admin_app.dependency_overrides[get_downstream_connector_probe] = ForbiddenProbe
    admin_headers = {"X-Access": json.dumps({"signature": "trusted", "claims": {"sub": "admin", "groups": ["admins"]}})}
    with TestClient(app) as client:
        connector_id = _create_connector(client, admin_headers, "oauth-personal")
        client.put(f"/api/admin/connectors/mcp/{connector_id}/publication", headers=admin_headers).raise_for_status()
        client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=admin_headers, json={
            "connectors": [{"connector_id": connector_id, "permission_status": "enabled"}],
        }).raise_for_status()
        client.put(f"/api/me/connectors/mcp/{connector_id}/enablement", headers={"X-Access": "alice"}, json={"enabled": True}).raise_for_status()
        yield OAuthApi(client, settings, provider, connector_id, admin_headers, app)


@pytest.mark.parametrize("body", [{"owner": "secret-canary"}, {"scope": "secret-canary"}, {"return_url": "secret-canary"}, [], None])
def test_start_requires_strict_empty_object(oauth_api: OAuthApi, body: object) -> None:
    response = oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice"}, json=body)
    assert response.status_code == 422
    assert "secret-canary" not in response.text
    assert not oauth_api.provider.preparations


@pytest.mark.parametrize("body,status", [(b"{" + b" " * 1024 + b"}", 413), (b"{\"secret-canary\":", 422), (b"", 422)])
def test_start_bounds_and_sanitizes_raw_body(oauth_api: OAuthApi, body: bytes, status: int) -> None:
    response = oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice", "Content-Type": "application/json"}, content=body)
    assert response.status_code == status
    assert "secret-canary" not in response.text
    assert not oauth_api.provider.preparations


@pytest.mark.parametrize("failure,status,code", [
    (PersonalOAuthProviderUnsupported("secret-provider-detail"), 422, "personal_oauth_provider_unsupported"),
    (PersonalOAuthProviderFailure("secret-provider-detail"), 502, "personal_oauth_provider_failure"),
    (ValueError("secret-provider-detail"), 502, "personal_oauth_provider_failure"),
])
def test_start_sanitizes_provider_failures(oauth_api: OAuthApi, failure: Exception, status: int, code: str) -> None:
    oauth_api.provider.preparation_failures.append(failure)
    response = oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice"}, json={})
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert "secret-provider-detail" not in response.text


def test_simultaneous_active_start_conflicts_without_second_registration(oauth_api: OAuthApi) -> None:
    oauth_api.start()
    assert oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice"}, json={}).status_code == 409
    assert len(oauth_api.provider.preparations) == 1


def test_start_requires_authentication_and_cookie_csrf(oauth_api: OAuthApi) -> None:
    assert oauth_api.client.post(oauth_api.url, json={}).status_code == 401
    assert oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice", "Cookie": "session=fixture"}, json={}).status_code == 403
    assert not oauth_api.provider.preparations


def test_oauth_policy_disabled_hides_routes_and_callback(oauth_api: OAuthApi) -> None:
    settings = AppConfig.model_validate({
        **oauth_api.settings.model_dump(),
        "personal_connections": {**oauth_api.settings.personal_connections.model_dump(), "oauth_enabled": False},
    })
    app = create_app(settings, [], user_verifier=UserVerifier())
    with TestClient(app) as client:
        assert client.post(oauth_api.url, headers={"X-Access": "alice"}, json={}).status_code == 404
        assert client.get(CALLBACK_PATH + "?state=secret-state&error=denied").status_code == 404


def test_attempt_status_and_cancel_are_owner_scoped_after_withdrawal(oauth_api: OAuthApi) -> None:
    attempt = oauth_api.start()
    url = oauth_api.url + "/" + attempt["attempt_id"]
    for method in (oauth_api.client.get, oauth_api.client.delete):
        assert method(url, headers={"X-Access": "bob"}).status_code == 404
    oauth_api.client.delete(f"/api/admin/connectors/mcp/{oauth_api.connector_id}/publication", headers=oauth_api.admin_headers).raise_for_status()
    status = oauth_api.client.get(url, headers={"X-Access": "alice"})
    assert status.json() == {key: value for key, value in attempt.items() if key != "authorization_url"}
    assert oauth_api.client.delete(url, headers={"X-Access": "alice"}).json()["status"] == "cancelled"
    assert oauth_api.client.get(oauth_api.callback()).status_code == 400
    assert not oauth_api.provider.exchanges


def test_callback_is_public_secret_free_and_exchanges_once(oauth_api: OAuthApi) -> None:
    attempt = oauth_api.start()
    response = oauth_api.client.get(oauth_api.callback())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "secret-code" not in response.text
    assert oauth_api.client.get(oauth_api.callback()).status_code == 400
    assert len(oauth_api.provider.exchanges) == 1
    status = oauth_api.client.get(oauth_api.url + "/" + attempt["attempt_id"], headers={"X-Access": "alice"})
    assert status.json()["status"] == "completed"
    selection = oauth_api.client.get(f"/api/me/connectors/mcp/{oauth_api.connector_id}", headers={"X-Access": "alice"}).json()
    assert selection["has_authorization"] is True
    assert selection["runtime_available"] is False


@pytest.mark.parametrize("suffix", ["&state=duplicate", "&return_url=https://evil.example", "&scope=unexpected", "&error=secret-canary", "&code=duplicate"])
def test_callback_rejects_ambiguous_unknown_or_scoped_responses(oauth_api: OAuthApi, suffix: str) -> None:
    oauth_api.start()
    response = oauth_api.client.get(oauth_api.callback() + suffix)
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert "secret-canary" not in response.text
    assert not oauth_api.provider.exchanges


def test_provider_exception_is_not_echoed_and_code_is_not_retried(oauth_api: OAuthApi) -> None:
    attempt = oauth_api.start()
    oauth_api.provider.fail_exchange = True
    response = oauth_api.client.get(oauth_api.callback())
    assert response.status_code == 400
    assert "secret-code" not in response.text
    assert "private-provider-context" not in response.text
    assert oauth_api.client.get(oauth_api.callback()).status_code == 400
    assert len(oauth_api.provider.exchanges) == 1
    assert oauth_api.client.get(oauth_api.url + "/" + attempt["attempt_id"], headers={"X-Access": "alice"}).json()["status"] == "failed"


def test_callback_after_new_application_uses_only_durable_context(oauth_api: OAuthApi) -> None:
    attempt = oauth_api.start()
    replacement_provider = FakeOAuthProvider()
    replacement_app = create_app(oauth_api.settings, [], user_verifier=UserVerifier())
    for route in replacement_app.routes:
        child = getattr(route, "app", None)
        if isinstance(child, FastAPI):
            child.dependency_overrides[get_personal_oauth_provider] = lambda: replacement_provider
    with TestClient(replacement_app) as client:
        assert client.get(oauth_api.callback()).status_code == 200
        assert client.get(oauth_api.url + "/" + attempt["attempt_id"], headers={"X-Access": "alice"}).json()["status"] == "completed"
    assert not replacement_provider.preparations
    assert len(replacement_provider.exchanges) == 1
    assert replacement_provider.exchanges[0].attempt.prepared.context.get_secret_value() == "private-provider-context"


@pytest.mark.parametrize("suffix", ["/", "/../docs", "/../openapi.json", "/unknown"])
def test_noncanonical_callbacks_do_not_redirect_or_expose_documentation(
    oauth_api: OAuthApi, suffix: str,
) -> None:
    response = oauth_api.client.get(
        CALLBACK_PATH + suffix, params={"state": "secret-canary", "error": "secret-canary"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "location" not in response.headers
    assert "no-store" in response.headers["cache-control"]
    assert "secret-canary" not in response.text


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("query", [b"state=secret-state&code=secret-code&iss=https%3A%2F%2Fissuer.example", b"state=secret-state&code=secret-code&state=duplicate", b"unknown=secret-code"])
@pytest.mark.parametrize("path,root_path", [
    (CALLBACK_PATH, ""),
    (CALLBACK_PATH + "/", ""),
    (CALLBACK_PATH.rsplit("/", 1)[0] + "/unknown", ""),
    (CALLBACK_PATH.rsplit("/", 1)[0], ""),
    ("/embedded" + CALLBACK_PATH, "/embedded"),
    ("/embedded" + CALLBACK_PATH + "/", "/embedded"),
    (CALLBACK_PATH, "/embedded"),
])
async def test_redaction_changes_original_scope_before_downstream_errors(
    query: bytes, path: str, root_path: str,
) -> None:
    original: Scope = {"type": "http", "path": path, "root_path": root_path, "query_string": query}

    async def failing_application(scope: Scope, receive: Receive, send: Send) -> None:
        assert scope is original
        assert scope["query_string"] == b""
        assert CALLBACK_QUERY_KEY in scope["state"]
        raise RuntimeError("routing failure")

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        return None

    middleware = PersonalOAuthQueryRedactionMiddleware(failing_application)
    with pytest.raises(RuntimeError, match="routing failure"):
        await middleware(original, receive, send)
    assert original["query_string"] == b""
