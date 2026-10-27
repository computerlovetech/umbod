from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.rest.main import create_app

BASE = "/api/me/filesystem"
POLICY = "/api/admin/filesystem/root-access"


@pytest.fixture
def local_filesystem_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "local-filesystem.sqlite")},
        runtime={"profile": "local", "auth": "dev"},
        admin_authentication={
            "mode": "simulation", "environment": "development", "simulated_admin": True,
            "simulated_user_id": "test-user", "membership_claim": "groups", "required_membership": "admin",
        },
        mcp={"permission_group_claim": "groups"},
    )


def test_local_filesystem_requires_explicit_root_grant_and_retains_private_ownership(
    local_filesystem_settings: AppConfig,
) -> None:
    with TestClient(create_app(local_filesystem_settings, [])) as client:
        initial = client.get(POLICY).json()
        assert initial["status"] == "uninitialized"
        assert set(initial) == {"status", "revision", "groups", "blocked_group_ids"}
        assert client.get(BASE + "/root").status_code == 403
        assert client.get(BASE + "/nodes?scope=owned").status_code == 501
        initial = client.get(POLICY).json()
        saved = client.put(POLICY, json={
            "expected_revision": initial["revision"], "groups": [{
                "group_id": "admin", "permissions": ["discover", "write"],
            }],
        })
        assert saved.status_code == 200
        root = client.get(BASE + "/root").json()
        created = client.post(BASE + f"/nodes/{root['id']}/directories", json={
            "name": "private-local-directory", "metadata": {"content_type": {}, "attributes": {}},
        })
        assert created.status_code == 201
        child = created.json()
        assert client.get(BASE + f"/nodes/{root['id']}/children").json() == {"nodes": [child]}
        revoked = client.put(POLICY, json={"expected_revision": saved.json()["revision"], "groups": []})
        assert revoked.status_code == 200
        assert client.get(BASE + "/root").status_code == 403
        assert client.get(BASE + f"/nodes/{child['id']}").json() == child
    other_settings = local_filesystem_settings.model_copy(update={
        "admin_authentication": local_filesystem_settings.admin_authentication.model_copy(update={"simulated_user_id": "other-user"}),
    })
    with TestClient(create_app(other_settings, [])) as other:
        assert other.get(BASE + f"/nodes/{child['id']}").status_code == 403


def test_local_filesystem_rejects_client_selected_issuer(
    local_filesystem_settings: AppConfig,
) -> None:
    with TestClient(create_app(local_filesystem_settings, [])) as client:
        initial = client.get(POLICY).json()
        saved = client.put(POLICY, json={
            "expected_revision": initial["revision"], "groups": [{
                "issuer": "attacker", "group_id": "admin", "permissions": ["discover", "write"],
            }],
        })
        assert saved.status_code == 422
        assert client.get(BASE + "/root", headers={
            "Authorization": 'Bearer {"iss":"attacker","sub":"test-user","groups":["admin"]}',
            "X-Umbod-Issuer": "attacker",
        }).status_code == 403
