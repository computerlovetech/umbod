from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.system_settings import read_raw_settings, save_raw_settings
from umbod.config import load_app_config_without_env_file
from umbod.infrastructure import AppPersistenceRuntime
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app, create_app_with_dependency_factories
from umbod.rest.settings import APISettings

from .conftest import jwt_headers

_SETTINGS_PATH = "/api/admin/system-settings/filesystem"
_FIELD = "require_mcp_file_deletion_approval"
_SET_FALSE = {_FIELD: {"operation": "set", "value": False}}
_RESET = {_FIELD: {"operation": "reset"}}


def test_get_returns_uncached_built_in_default(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.get(_SETTINGS_PATH, headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {_FIELD: {"value": True, "source": "built_in_default"}}


def test_explicit_false_is_shared_across_clients(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    updated = client.patch(_SETTINGS_PATH, json=_SET_FALSE, headers=admin_headers)
    with closing(TestClient(client.app)) as other:
        fetched = other.get(
            _SETTINGS_PATH, headers=jwt_headers("second-admin", "umbod-admins")
        )

    assert updated.status_code == fetched.status_code == 200
    assert updated.headers["Cache-Control"] == "no-store"
    assert (
        updated.json()
        == fetched.json()
        == {_FIELD: {"value": False, "source": "admin_override"}}
    )


def test_simulated_admin_reset_uses_startup_deployment_default(
    availability: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "dev")
    monkeypatch.setenv("UMBOD_REQUIRE_MCP_FILE_DELETION_APPROVAL", "off")
    settings = load_app_config_without_env_file()
    settings.rest.metrics_enabled = False
    with TestClient(create_app(settings, [])) as client:
        deployment_default = {_FIELD: {"value": False, "source": "deployment_default"}}
        assert client.get(_SETTINGS_PATH).json() == deployment_default

        updated = client.patch(
            _SETTINGS_PATH, json={_FIELD: {"operation": "set", "value": True}}
        )
        assert updated.json() == {_FIELD: {"value": True, "source": "admin_override"}}

        reset = client.patch(_SETTINGS_PATH, json=_RESET)
        repeated = client.patch(_SETTINGS_PATH, json=_RESET)

        assert reset.status_code == repeated.status_code == 200
        assert reset.json() == repeated.json() == deployment_default


@pytest.mark.parametrize(
    "body",
    [
        "",
        "{",
        b'{"invalid_utf8":"\xff"}',
        "null",
        "{}",
        '{"unknown":{"operation":"reset"}}',
        '{"require_mcp_file_deletion_approval":null}',
        '{"require_mcp_file_deletion_approval":{"operation":"set"}}',
        '{"require_mcp_file_deletion_approval":{"operation":"set","value":"false"}}',
        '{"require_mcp_file_deletion_approval":{"operation":"set","value":0}}',
        '{"require_mcp_file_deletion_approval":{"operation":"set","value":NaN}}',
        '{"require_mcp_file_deletion_approval":{"operation":"reset","value":null}}',
        '{"require_mcp_file_deletion_approval":{"operation":"unknown"}}',
    ],
)
def test_invalid_patch_preserves_override(
    client: TestClient, admin_headers: dict[str, str], body: str | bytes
) -> None:
    saved = client.patch(_SETTINGS_PATH, json=_SET_FALSE, headers=admin_headers)

    response = client.patch(
        _SETTINGS_PATH,
        content=body,
        headers={**admin_headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get(_SETTINGS_PATH, headers=admin_headers).json() == saved.json()


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_unregistered_sections_are_not_dispatched(
    client: TestClient,
    admin_headers: dict[str, str],
    method: str,
) -> None:
    response = client.request(
        method, "/api/admin/system-settings/unknown", headers=admin_headers, content="{"
    )
    assert response.status_code == 404


def test_filesystem_section_has_typed_admin_openapi(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    schema = client.get("/api/admin/openapi.json", headers=admin_headers).json()
    path = schema["paths"]["/system-settings/filesystem"]
    request_schema = path["patch"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert request_schema["$ref"].endswith("/FilesystemSettingsPatch")
    field = schema["components"]["schemas"]["FilesystemSettingsPatch"]["properties"][
        _FIELD
    ]
    assert field["discriminator"]["propertyName"] == "operation"
    for method in ("get", "patch"):
        response_schema = path[method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith("/FilesystemSettingsResponse")


@pytest.mark.parametrize(
    "method,body", [("GET", None), ("PATCH", _SET_FALSE), ("PATCH", _RESET)]
)
def test_corrupt_persisted_settings_return_503_without_repair(
    jwt_settings: APISettings,
    admin_headers: dict[str, str],
    method: str,
    body: dict[str, object] | None,
) -> None:
    jwt_settings.filesystem.require_mcp_file_deletion_approval = False
    corrupt_document = {_FIELD: "not-a-boolean"}
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(jwt_settings, runtime, [])

    with TestClient(create_app_with_dependency_factories(factories)) as client:
        assert client.portal is not None
        client.portal.call(save_raw_settings, runtime.database, corrupt_document)
        response = client.request(
            method, _SETTINGS_PATH, json=body, headers=admin_headers
        )
        stored = client.portal.call(read_raw_settings, runtime.database)

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "system_settings_unavailable"}}
    assert response.headers["Cache-Control"] == "no-store"
    assert stored == [corrupt_document]


class UnavailableReadiness:
    async def ensure_ready(self) -> None:
        raise OSError("Private storage information")


class UnexpectedReadiness:
    async def ensure_ready(self) -> None:
        pytest.fail("Rejected requests must not reach persistence readiness")


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_request_time_readiness_failure_is_sanitized(
    jwt_settings: APISettings,
    admin_headers: dict[str, str],
    method: str,
) -> None:
    runtime = AppPersistenceRuntime(create_inmemory_runtime().database, UnavailableReadiness())
    factories = ConnectorApiDependencyFactories.from_settings(jwt_settings, runtime, [])
    with closing(TestClient(create_app_with_dependency_factories(factories))) as client:
        response = client.request(
            method, _SETTINGS_PATH, json=_RESET, headers=admin_headers
        )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "system_settings_unavailable"}}
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize(
    "access,status", [("anonymous", 401), ("non-admin", 403), ("disabled", 401)]
)
def test_access_denials_do_not_reach_settings_storage(
    jwt_settings: APISettings, method: str, access: str, status: int
) -> None:
    if access == "disabled":
        jwt_settings.admin_authentication.mode = "disabled"
    headers = {"X-Umbod-Role": "administrator"}
    if access != "anonymous":
        headers.update(
            jwt_headers(
                "caller", "umbod-users" if access == "non-admin" else "umbod-admins"
            )
        )
    runtime = AppPersistenceRuntime(create_inmemory_runtime().database, UnexpectedReadiness())
    factories = ConnectorApiDependencyFactories.from_settings(jwt_settings, runtime, [])
    with closing(TestClient(create_app_with_dependency_factories(factories))) as client:
        response = client.request(method, _SETTINGS_PATH, headers=headers, json=_RESET)

    assert response.status_code == status


def test_disabled_admin_auth_rejects_malformed_patch_before_validation(
    jwt_settings: APISettings,
) -> None:
    jwt_settings.admin_authentication.mode = "disabled"
    runtime = AppPersistenceRuntime(create_inmemory_runtime().database, UnexpectedReadiness())
    factories = ConnectorApiDependencyFactories.from_settings(jwt_settings, runtime, [])
    with closing(TestClient(create_app_with_dependency_factories(factories))) as client:
        response = client.patch(
            _SETTINGS_PATH, content="{", headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


def test_cookie_patch_requires_trusted_origin_and_marker(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    headers = {**admin_headers, "Cookie": "gateway=session"}
    rejected = client.patch(_SETTINGS_PATH, json=_SET_FALSE, headers=headers)
    assert rejected.status_code == 403
    assert client.get(_SETTINGS_PATH, headers=admin_headers).json() == {
        _FIELD: {"value": True, "source": "built_in_default"}
    }

    accepted = client.patch(
        _SETTINGS_PATH,
        json=_SET_FALSE,
        headers={
            **headers,
            "Origin": "https://site.example.com",
            "X-Umbod-Web-Request": "1",
        },
    )
    assert accepted.status_code == 200
