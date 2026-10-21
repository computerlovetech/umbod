from pathlib import Path

import pytest
from pydantic import ValidationError

from umbod.config import AppConfig
from umbod.config.derive import build_app_config
from umbod.config.inspection import inspect_app_config
from umbod.config.operator import OperatorSettings


def test_unconfigured_deployment_keeps_personal_oauth_unavailable() -> None:
    assert not AppConfig().personal_connections.oauth_enabled
    assert not build_app_config(OperatorSettings(_env_file=None)).personal_connections.oauth_enabled


def test_personal_oauth_authorization_requires_catalogue_policy() -> None:
    with pytest.raises(ValidationError, match="personal connections to be enabled"):
        AppConfig.model_validate({"personal_connections": {"oauth_enabled": True}})


@pytest.mark.parametrize(
    "storage",
    [
        {"type": "inmemory"},
        {"type": "sqlite", "sqlite_path": ""},
        {"type": "sqlite", "sqlite_path": " "},
        {"type": "sqlite", "sqlite_path": ":memory:"},
        {"type": "sqlite", "sqlite_path": "file::memory:"},
        {"type": "sqlite", "sqlite_path": "file:attempts?mode=memory"},
    ],
)
def test_personal_oauth_authorization_rejects_nondurable_storage(storage: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="persistent SQLite"):
        AppConfig.model_validate({
            "personal_connections": {
                "enabled": True, "identity_namespace": "test:oauth", "oauth_enabled": True,
            },
            "connector_store": storage,
        })


def test_personal_oauth_authorization_rejects_an_empty_encryption_secret(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="configured encryption secret"):
        AppConfig.model_validate({
            "personal_connections": {
                "enabled": True, "identity_namespace": "test:oauth", "oauth_enabled": True,
            },
            "connector_store": {"type": "sqlite", "sqlite_path": str(tmp_path / "oauth.sqlite")},
        })


def test_personal_oauth_environment_and_nonsecret_inspection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_ENABLED", "true")
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE", "test:oauth")
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED", "true")
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "runtime-personal-oauth-policy-test-secret")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "sqlite")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE_SQLITE_PATH", str(tmp_path / "oauth.sqlite"))
    settings = build_app_config(OperatorSettings(_env_file=None))
    assert settings.personal_connections.oauth_enabled
    entries = {
        entry.variable: entry.value
        for group in inspect_app_config(settings).groups
        for entry in group.entries
    }
    assert entries["UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED"] is True
