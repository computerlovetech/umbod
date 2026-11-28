import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.persistence_runtime import create_inmemory_runtime
from tests.support.system_settings import save_raw_settings
from tests.umbod.infrastructure.portable_connectors.fixtures.configuration_probe import (
    connector,
)
from umbod.core.connectors.portable.draft_validation.models import (
    ValidatedManifestSnapshot,
)
from umbod.core.connectors.portable.drafts import DraftReceipt
from umbod.core.connectors.portable.managed import DatabaseManagedConnectorStore
from umbod.core.connectors.portable.managed.configuration_schema import (
    inactive_connector_snapshot,
)
from umbod.core.connectors.portable.managed.models import PortableConnectorSubmission
from umbod.core.persistence import DatabaseSession, PersistenceRuntime, TransactionMode
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories
from umbod.rest.settings import APISettings

_BASE = "/api/admin/portable-connectors"
_SETTINGS = "/api/admin/system-settings/portable-connectors"
_VALID = {"workspace": "demo", "mode": "preview"}


@dataclass(frozen=True)
class PortableAdmin:
    client: TestClient
    runtime: PersistenceRuntime
    connector_id: UUID
    private_revision: DraftReceipt

    @property
    def url(self) -> str:
        return f"{_BASE}/{self.connector_id}/configuration"


def _headers(group: str) -> dict[str, str]:
    token = json.dumps(
        {"signature": "trusted", "claims": {"sub": "private-actor", "groups": [group]}}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> APISettings:
    deployment = tmp_path / "availability.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return APISettings(
        rest={"metrics_enabled": False},
        admin_authentication={
            "mode": "jwt",
            "environment": "development",
            "jwt_header_name": "Authorization",
        },
        endpoints={"site_base_url": "https://site.example.com"},
    )


@pytest.fixture
def portable_admin(settings: APISettings) -> Iterator[PortableAdmin]:
    with _portable_admin(settings) as admin:
        yield admin


@contextmanager
def _portable_admin(settings: APISettings) -> Iterator[PortableAdmin]:
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, [])
    manifest = connector.manifest()
    snapshot = inactive_connector_snapshot(
        ValidatedManifestSnapshot(
            manifest_version=manifest["manifest_version"],
            connector_id=manifest["connector_id"],
            display_name=manifest["display_name"],
            description=manifest["description"],
            configuration_schema_json=json.dumps(manifest["configuration_schema"]),
        )
    )
    revision = DraftReceipt(uuid4(), uuid4(), "0" * 64)
    submission = PortableConnectorSubmission(revision, "private-profile", snapshot)
    with TestClient(create_app_with_dependency_factories(factories)) as client:
        assert client.portal is not None
        receipt = client.portal.call(
            DatabaseManagedConnectorStore(runtime.database).submit, submission
        )
        yield PortableAdmin(client, runtime, receipt.connector_id, revision)


def test_existing_submission_exposes_only_admin_summary_and_pinned_fields(
    portable_admin: PortableAdmin,
) -> None:
    client = portable_admin.client
    headers = _headers("umbod-admins")
    listed = client.get(_BASE, headers=headers)
    configuration = client.get(portable_admin.url, headers=headers)
    summary = {
        "connector_id": str(portable_admin.connector_id),
        "name": "Configuration probe",
        "description": "Verifies inactive portable connector configuration.",
        "status": "inactive",
        "configured": False,
    }
    assert listed.status_code == configuration.status_code == 200
    assert (
        listed.headers["Cache-Control"]
        == configuration.headers["Cache-Control"]
        == "no-store"
    )
    assert listed.json() == {"connectors": [summary]}
    detail = configuration.json()
    assert {
        "connector": detail["connector"],
        "configuration": detail["configuration"],
    } == {
        "connector": summary,
        "configuration": None,
    }
    assert sorted(detail["fields"], key=lambda field: field["name"]) == [
        {
            "name": "mode",
            "label": "Mode",
            "required": True,
            "min_length": 0,
            "max_length": 1024,
            "choices": ["preview", "review"],
        },
        {
            "name": "workspace",
            "label": "Workspace",
            "required": True,
            "min_length": 1,
            "max_length": 1024,
            "choices": [],
        },
    ]
    assert set(detail) == {"connector", "configuration", "fields"}


@pytest.mark.parametrize("enabled", [False, "invalid-flag-value"])
def test_off_or_unreadable_creation_gate_does_not_prevent_admin_configuration(
    portable_admin: PortableAdmin,
    enabled: bool | str,
) -> None:
    client = portable_admin.client
    headers = _headers("umbod-admins")
    if isinstance(enabled, bool):
        assert (
            client.patch(
                _SETTINGS, json={"enabled": enabled}, headers=headers
            ).status_code
            == 200
        )
    else:
        assert client.portal is not None
        client.portal.call(
            save_raw_settings,
            portable_admin.runtime.database,
            {"portable_connectors_enabled": enabled},
        )

    updated = client.put(
        portable_admin.url, json={"configuration": _VALID}, headers=headers
    )

    assert updated.status_code == 200
    assert updated.json()["configuration"] == _VALID
    assert updated.json()["connector"]["status"] == "inactive"
    assert updated.json()["connector"]["configured"] is True
    assert client.get(portable_admin.url, headers=headers).json() == updated.json()
    assert client.get(_BASE, headers=headers).json() == {
        "connectors": [updated.json()["connector"]]
    }


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (
            '{"configuration":{"mode":"preview"}}',
            {"code": "required_field", "field": "workspace"},
        ),
        (
            '{"configuration":{"workspace":"","mode":"preview"}}',
            {"code": "invalid_length", "field": "workspace"},
        ),
        (
            '{"configuration":{"workspace":"demo","mode":"private-rejected-value"}}',
            {"code": "invalid_choice", "field": "mode"},
        ),
        (
            '{"configuration":{"workspace":"demo","mode":12}}',
            {"code": "invalid_type", "field": "mode"},
        ),
        (
            '{"configuration":{"workspace":"demo","mode":"review","private-unknown-field":"private-rejected-value"}}',
            {"code": "unknown_field"},
        ),
        (
            '{"configuration":{"workspace":"demo","mode":"preview","mode":"review"}}',
            {"code": "invalid_configuration"},
        ),
        (
            '{"configuration":{"workspace":"demo","mode":"preview"},"extra":"private"}',
            {"code": "invalid_configuration"},
        ),
        ('{"configuration":null}', {"code": "invalid_configuration"}),
        (
            '{"configuration":{"workspace":"first\\nsecond","mode":"preview"}}',
            {"code": "invalid_value", "field": "workspace"},
        ),
        (
            '{"configuration":{"mode":"review","workspace":"' + "x" * 1025 + '"}}',
            {"code": "invalid_length", "field": "workspace"},
        ),
        (
            '{"configuration":{"workspace":"\\ud800","mode":"preview"}}',
            {"code": "invalid_value", "field": "workspace"},
        ),
        (" " * 220_000, {"code": "configuration_too_large"}),
    ],
)
def test_invalid_save_uses_safe_guidance_and_preserves_configuration(
    portable_admin: PortableAdmin,
    body: str,
    error: dict[str, str],
) -> None:
    client = portable_admin.client
    headers = _headers("umbod-admins")
    saved = client.put(
        portable_admin.url, json={"configuration": _VALID}, headers=headers
    )
    assert saved.status_code == 200

    denied = client.put(
        portable_admin.url,
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )

    assert denied.status_code == 422
    assert denied.json() == {"detail": error}
    assert denied.headers["Cache-Control"] == "no-store"
    assert client.get(portable_admin.url, headers=headers).json() == saved.json()


def test_unconfirmed_write_returns_safe_reload_guidance_and_no_success(
    portable_admin: PortableAdmin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = portable_admin.client
    headers = _headers("umbod-admins")
    saved = client.put(
        portable_admin.url, json={"configuration": _VALID}, headers=headers
    )
    assert saved.status_code == 200
    database = portable_admin.runtime.database
    original_session = database.session

    @asynccontextmanager
    async def failed_commit(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with original_session(mode=mode) as session:
            yield session
            raise RuntimeError("private storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(database, "session", failed_commit)
        result = client.put(
            portable_admin.url,
            json={"configuration": {"workspace": "replacement", "mode": "review"}},
            headers=headers,
        )

    assert result.status_code == 503
    assert result.json() == {
        "detail": {
            "code": "configuration_write_unconfirmed",
            "message": "Reload the configuration before retrying.",
        }
    }
    assert client.get(portable_admin.url, headers=headers).json() == saved.json()


@pytest.mark.parametrize(("group", "status"), [("umbod-users", 403), ("", 401)])
def test_non_admin_is_denied_at_every_route(
    portable_admin: PortableAdmin, group: str, status: int
) -> None:
    client = portable_admin.client
    headers = _headers(group) if group else {}

    assert client.get(_BASE, headers=headers).status_code == status
    assert client.get(portable_admin.url, headers=headers).status_code == status
    assert (
        client.put(
            portable_admin.url, json={"configuration": _VALID}, headers=headers
        ).status_code
        == status
    )
    assert (
        client.get(portable_admin.url, headers=_headers("umbod-admins")).json()[
            "configuration"
        ]
        is None
    )


def test_disabled_admin_middleware_never_opens_catalog_or_configuration(
    settings: APISettings,
) -> None:
    settings.admin_authentication.mode = "disabled"
    with _portable_admin(settings) as admin:
        headers = _headers("umbod-admins")
        assert admin.client.get(_BASE, headers=headers).status_code == 401
        assert admin.client.get(admin.url, headers=headers).status_code == 401
        assert (
            admin.client.put(
                admin.url, json={"configuration": _VALID}, headers=headers
            ).status_code
            == 401
        )


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_unknown_or_private_revision_identity_returns_safe_not_found(
    portable_admin: PortableAdmin, method: str
) -> None:
    for unknown in (
        uuid4(),
        portable_admin.private_revision.revision_id,
        portable_admin.private_revision.draft_id,
        "not-a-uuid",
    ):
        response = portable_admin.client.request(
            method,
            f"{_BASE}/{unknown}/configuration",
            json={"configuration": _VALID},
            headers=_headers("umbod-admins"),
        )
        assert response.status_code == 404
        assert response.json() == {"detail": {"code": "portable_connector_not_found"}}
