import pytest
from fastapi.testclient import TestClient

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.system_settings import save_raw_settings
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app, create_app_with_dependency_factories
from umbod.rest.settings import APISettings

_PORTABLE_PATH = "/api/admin/system-settings/portable-connectors"
_FILESYSTEM_PATH = "/api/admin/system-settings/filesystem"
_APPROVAL_FIELD = "require_mcp_file_deletion_approval"


def test_get_returns_uncached_default_off(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.get(_PORTABLE_PATH, headers=admin_headers)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"enabled": False}


def test_flag_round_trips_on_and_off_without_changing_saved_approval(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    approval = client.patch(
        _FILESYSTEM_PATH,
        json={_APPROVAL_FIELD: {"operation": "set", "value": False}},
        headers=admin_headers,
    )
    assert approval.json() == {
        _APPROVAL_FIELD: {"value": False, "source": "admin_override"}
    }

    for enabled in (True, False):
        response = client.patch(
            _PORTABLE_PATH, json={"enabled": enabled}, headers=admin_headers
        )

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json() == {"enabled": enabled}
        assert (
            client.get(_PORTABLE_PATH, headers=admin_headers).json() == response.json()
        )
        assert (
            client.get(_FILESYSTEM_PATH, headers=admin_headers).json()
            == approval.json()
        )


@pytest.mark.parametrize(
    ("deployment_value", "fallback_value", "source"),
    [(None, True, "built_in_default"), (False, False, "deployment_default")],
)
def test_portable_only_row_preserves_approval_fallback_after_save_and_reset(
    jwt_settings: APISettings,
    admin_headers: dict[str, str],
    deployment_value: bool | None,
    fallback_value: bool,
    source: str,
) -> None:
    jwt_settings.filesystem.require_mcp_file_deletion_approval = deployment_value
    with TestClient(create_app(jwt_settings, [])) as client:
        fallback = {_APPROVAL_FIELD: {"value": fallback_value, "source": source}}
        enabled = client.patch(
            _PORTABLE_PATH, json={"enabled": True}, headers=admin_headers
        )
        assert enabled.status_code == 200
        assert client.get(_FILESYSTEM_PATH, headers=admin_headers).json() == fallback

        override = client.patch(
            _FILESYSTEM_PATH,
            json={_APPROVAL_FIELD: {"operation": "set", "value": not fallback_value}},
            headers=admin_headers,
        )
        assert override.json() == {
            _APPROVAL_FIELD: {"value": not fallback_value, "source": "admin_override"}
        }
        assert (
            client.get(_PORTABLE_PATH, headers=admin_headers).json() == enabled.json()
        )

        reset = client.patch(
            _FILESYSTEM_PATH,
            json={_APPROVAL_FIELD: {"operation": "reset"}},
            headers=admin_headers,
        )
        assert reset.json() == fallback
        assert client.get(_FILESYSTEM_PATH, headers=admin_headers).json() == fallback
        assert (
            client.get(_PORTABLE_PATH, headers=admin_headers).json() == enabled.json()
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"enabled": "true"},
        {"enabled": 0},
        {"enabled": None},
        {"enabled": True, "unexpected": True},
    ],
)
def test_patch_rejects_non_boolean_or_extra_fields(
    client: TestClient, admin_headers: dict[str, str], payload: dict[str, object]
) -> None:
    response = client.patch(_PORTABLE_PATH, json=payload, headers=admin_headers)

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get(_PORTABLE_PATH, headers=admin_headers).json() == {
        "enabled": False
    }


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize(("authenticated", "status"), [(False, 401), (True, 403)])
def test_requests_require_administrator_access(
    client: TestClient,
    admin_headers: dict[str, str],
    member_headers: dict[str, str],
    method: str,
    authenticated: bool,
    status: int,
) -> None:
    response = client.request(
        method,
        _PORTABLE_PATH,
        json={"enabled": True},
        headers=member_headers if authenticated else {},
    )

    assert response.status_code == status
    assert client.get(_PORTABLE_PATH, headers=admin_headers).json() == {
        "enabled": False
    }


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_invalid_persisted_value_returns_sanitized_storage_error(
    jwt_settings: APISettings, admin_headers: dict[str, str], method: str
) -> None:
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(jwt_settings, runtime, [])

    with TestClient(create_app_with_dependency_factories(factories)) as client:
        assert client.portal is not None
        client.portal.call(
            save_raw_settings,
            runtime.database,
            {"portable_connectors_enabled": "false"},
        )
        response = client.request(
            method, _PORTABLE_PATH, json={"enabled": True}, headers=admin_headers
        )

    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"detail": {"code": "system_settings_unavailable"}}
