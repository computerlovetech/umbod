import json
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager, closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.persistence_runtime import create_inmemory_runtime
from umbod.config import load_app_config_without_env_file
from umbod.core.persistence import ReadSession
from umbod.infrastructure import AppPersistenceRuntime
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app, create_app_with_dependency_factories
from umbod.rest.settings import APISettings

_PATH = "/api/admin/system-settings/provider-group-mappings"
_GROUPS = "/api/admin/groups"
_FILESYSTEM = "/api/admin/system-settings/filesystem"
_ENV = "UMBOD_PROVIDER_GROUP_OVERRIDES"
_RULE = {
    "external_value": " Staff ",
    "group_id": "umbod-admins",
}
_RESET = {"operation": "reset"}
_UNAVAILABLE = {"detail": {"code": "system_settings_unavailable"}}


def _headers(group: str) -> dict[str, str]:
    token = json.dumps(
        {"signature": "trusted", "claims": {"sub": group, "groups": [group]}}
    )
    return {"Authorization": f"Bearer {token}"}


_ADMIN = _headers("umbod-admins")


@pytest.fixture
def runtime_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    availability = tmp_path / "availability.json"
    availability.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability)
    )
    monkeypatch.delenv(_ENV, raising=False)


def _settings(auth_mode: str = "jwt") -> APISettings:
    settings = load_app_config_without_env_file()
    settings.rest.metrics_enabled = False
    settings.admin_authentication.mode = auth_mode
    settings.admin_authentication.jwt_header_name = "Authorization"
    return settings


def _client(auth_mode: str = "jwt") -> TestClient:
    return TestClient(create_app(_settings(auth_mode), []))


@pytest.fixture
def client(runtime_environment: None) -> Iterator[TestClient]:
    with _client() as transport:
        yield transport


def _set(client: TestClient, *mappings: dict[str, str]) -> dict[str, object]:
    response = client.patch(
        _PATH, json={"operation": "set", "mappings": mappings}, headers=_ADMIN
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def _register(client: TestClient, group_id: str) -> None:
    assert (
        client.post(_GROUPS, json={"group_id": group_id}, headers=_ADMIN).status_code
        == 204
    )


def test_admin_route_returns_uncached_built_in_default(client: TestClient) -> None:
    response = client.get(_PATH, headers=_ADMIN)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"mappings": [], "source": "built_in_default"}


def test_inherits_resolved_issuer_and_permission_claim_until_override_and_regenerates_on_reset(
    runtime_environment: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "auth0")
    monkeypatch.setenv("UMBOD_OIDC_DOMAIN", "legacy-issuer.example")
    monkeypatch.setenv("UMBOD_OIDC_ISSUER_URL", "")
    monkeypatch.setenv("UMBOD_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("UMBOD_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("UMBOD_OIDC_AUDIENCE", "test-audience")
    monkeypatch.setenv("UMBOD_ADMIN_MEMBERSHIP_CLAIM", "groups")
    monkeypatch.setenv("UMBOD_MCP_PERMISSION_CLAIM", "https://example.test/claims/teams")
    group_id = " Team / Read "
    inherited = {
        "external_value": group_id,
        "group_id": group_id,
    }
    with _client() as client:
        registered_before = client.get(_GROUPS, headers=_ADMIN).json()["groups"]
        assert registered_before == []
        _register(client, group_id)
        assert client.get(_PATH, headers=_ADMIN).json() == {
            "mappings": [inherited], "source": "inherited_claim_default",
        }

        saved = _set(client, {**inherited, "external_value": "external helpdesk group"})
        _register(client, "another-team")
        assert client.get(_PATH, headers=_ADMIN).json() == saved

        restored = client.patch(_PATH, json=_RESET, headers=_ADMIN)
        assert restored.status_code == 200
        assert restored.json() == {
            "mappings": [inherited, {**inherited, "external_value": "another-team", "group_id": "another-team"}],
            "source": "inherited_claim_default",
        }


def test_top_level_patch_contract_is_discriminated_in_admin_openapi(
    client: TestClient,
) -> None:
    schema = client.get("/api/admin/openapi.json", headers=_ADMIN).json()
    path = schema["paths"]["/system-settings/provider-group-mappings"]
    request = path["patch"]["requestBody"]["content"]["application/json"]["schema"]
    assert request["discriminator"]["propertyName"] == "operation"
    assert set(request["discriminator"]["mapping"]) == {"set", "reset"}
    schemas = schema["components"]["schemas"]
    mapping = schemas["ProviderGroupMapping"]
    assert set(mapping["required"]) == set(mapping["properties"]) == {"external_value", "group_id"}
    assert mapping["additionalProperties"] is False
    target = mapping["properties"]["group_id"]
    assert schemas[target["$ref"].rsplit("/", 1)[-1]]["type"] == "string"


def test_set_preserves_fan_out_literal_fields_and_order(client: TestClient) -> None:
    _register(client, _RULE["group_id"])
    _register(client, " Team ")
    rules = [
        {**_RULE, "group_id": " Team "},
        _RULE,
        {**_RULE, "external_value": "STAFF"},
    ]

    assert _set(client, *rules) == {"mappings": rules, "source": "admin_override"}
    assert client.get(_PATH, headers=_ADMIN).json() == {
        "mappings": rules,
        "source": "admin_override",
    }


def test_unknown_targets_are_reported_by_index_without_replacing_override(
    client: TestClient,
) -> None:
    _register(client, _RULE["group_id"])
    saved = _set(client, _RULE)
    response = client.patch(
        _PATH,
        json={
            "operation": "set",
            "mappings": [
                _RULE,
                {**_RULE, "group_id": "private-unregistered-id"},
            ],
        },
        headers=_ADMIN,
    )

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["detail"][0]["loc"] == ["body", "mappings", 1, "group_id"]
    assert "private-unregistered-id" not in response.text
    assert client.get(_PATH, headers=_ADMIN).json() == saved


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b'{"operation":"set","mappings":"\xff"}',
        b"null",
        b'{"operation":"reset","mappings":[]}',
        b'{"operation":"set"}',
        b'{"operation":"set","mappings":{}}',
        b'{"operation":"set","mappings":null}',
        json.dumps({"operation": "set", "mappings": [_RULE, _RULE]}),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "group_id": " \t "}]}),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "group_id": 1}]}),
        json.dumps(
            {"operation": "set", "mappings": [{key: value for key, value in _RULE.items() if key != "group_id"}]}
        ),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "claim": "groups"}]}),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "issuer": "https://issuer.example/"}]}),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "external_value": " \t "}]}),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "external_value": 1}]}),
        json.dumps({"operation": "set", "mappings": [{**_RULE, "external_value": "\ud800"}]}),
        json.dumps(
            {
                "operation": "set",
                "mappings": [{**_RULE, "private-input": "private-input"}],
            }
        ),
        json.dumps(
            {
                "operation": "set",
                "mappings": [{"group_id": "g"}],
            }
        ),
    ],
)
def test_invalid_patches_are_sanitized_and_preserve_override(
    client: TestClient, body: str | bytes
) -> None:
    _register(client, _RULE["group_id"])
    saved = _set(client, _RULE)
    response = client.patch(
        _PATH, content=body, headers={**_ADMIN, "Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert "private-input" not in response.text
    assert all("input" not in issue for issue in response.json()["detail"])
    assert client.get(_PATH, headers=_ADMIN).json() == saved


@pytest.mark.parametrize(("path", "body"), [
    (f"{_GROUPS}/mapping-target", None),
    (_GROUPS, {"group_id": "mapping-target"}),
    ("/api/admin/mcp-permissions/groups/mapping-target", None),
])
def test_deletion_rejects_live_mapping_targets(
    client: TestClient, path: str, body: dict[str, str] | None,
) -> None:
    _register(client, "mapping-target")
    saved = _set(client, {**_RULE, "group_id": "mapping-target"})

    response = client.request("DELETE", path, json=body, headers=_ADMIN)

    assert response.status_code == 409
    assert "live provider group overrides" in response.json()["detail"]
    assert client.get(_PATH, headers=_ADMIN).json() == saved


def test_reset_releases_mapping_target_for_deletion(client: TestClient) -> None:
    _register(client, "mapping-target")
    _set(client, {**_RULE, "group_id": "mapping-target"})
    assert client.patch(_PATH, json=_RESET, headers=_ADMIN).status_code == 200

    assert client.delete(f"{_GROUPS}/mapping-target", headers=_ADMIN).status_code == 204


def test_invalid_deployment_is_masked_but_blocks_reset_without_affecting_approval(
    runtime_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ENV, "{private-input")
    with _client() as client:
        missing = client.get(_PATH, headers=_ADMIN)
        assert missing.status_code == 503
        assert missing.json() == _UNAVAILABLE
        assert missing.headers["Cache-Control"] == "no-store"
        saved = _set(client)
        assert client.get(_PATH, headers=_ADMIN).json() == saved

        reset = client.patch(_PATH, json=_RESET, headers=_ADMIN)
        assert reset.status_code == 503
        assert reset.json() == _UNAVAILABLE
        assert reset.headers["Cache-Control"] == "no-store"
        assert client.get(_PATH, headers=_ADMIN).json() == saved
        assert client.get(_FILESYSTEM, headers=_ADMIN).status_code == 200


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_provider_claim_mapping_does_not_grant_admin_access(
    client: TestClient, method: str
) -> None:
    user = _headers("provider-staff")
    assert client.request(method, _PATH, json=_RESET, headers=user).status_code == 403
    _register(client, _RULE["group_id"])
    saved = _set(client, {**_RULE, "external_value": "provider-staff"})

    assert client.request(method, _PATH, json=_RESET, headers=user).status_code == 403
    assert client.get(_PATH, headers=_ADMIN).json() == saved


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize("mode", ["jwt", "disabled"])
def test_non_authenticated_or_disabled_mode_cannot_use_resource(
    runtime_environment: None,
    method: str,
    mode: str,
) -> None:
    headers = _ADMIN if mode == "disabled" else {}
    with _client(mode) as client:
        assert (
            client.request(method, _PATH, json=_RESET, headers=headers).status_code
            == 401
        )


def test_database_read_failure_does_not_return_deployment_default(
    runtime_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_ENV, "[]")
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(_settings(), runtime, [])

    def fail_read() -> AbstractAsyncContextManager[ReadSession]:
        raise OSError("Private storage information")

    with TestClient(create_app_with_dependency_factories(factories)) as client:
        monkeypatch.setattr(runtime.database, "read_session", fail_read)
        response = client.get(_PATH, headers=_ADMIN)

    assert response.status_code == 503
    assert response.json() == _UNAVAILABLE
    assert response.headers["Cache-Control"] == "no-store"


class UnavailableReadiness:
    async def ensure_ready(self) -> None:
        raise OSError("Private readiness information")


def test_request_time_readiness_failure_is_sanitized(runtime_environment: None) -> None:
    runtime = AppPersistenceRuntime(
        create_inmemory_runtime().database, UnavailableReadiness()
    )
    factories = ConnectorApiDependencyFactories.from_settings(_settings(), runtime, [])
    with closing(TestClient(create_app_with_dependency_factories(factories))) as client:
        response = client.patch(_PATH, json=_RESET, headers=_ADMIN)

    assert response.status_code == 503
    assert response.json() == _UNAVAILABLE
    assert response.headers["Cache-Control"] == "no-store"
