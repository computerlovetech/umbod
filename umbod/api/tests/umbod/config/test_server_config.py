import os
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from umbod.config import OperatorSettings, load_app_config, load_server_app_config
from umbod.config import derive
from umbod.config.server_settings import ServerRootSettings


@pytest.fixture(autouse=True)
def isolated_operator_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in os.environ:
        if name.startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("invalid_setting", [None, "UMBOD_REST_PORT", "UMBOD_MCP_PORT", "UMBOD_OTLP_ENABLED"])
@pytest.mark.parametrize("secret", [None, "", " ", "\t\r\n"])
@pytest.mark.parametrize("profile", ["local", "production"])
def test_server_loader_rejects_blank_root_before_profile_derivation(
    monkeypatch: pytest.MonkeyPatch, secret: Optional[str], profile: str, invalid_setting: Optional[str]
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", profile)
    if invalid_setting is not None:
        monkeypatch.setenv(invalid_setting, "invalid")
    monkeypatch.setenv("UMBOD_OIDC_CLIENT_SECRET", "must-not-be-disclosed")
    if secret is not None:
        monkeypatch.setenv("UMBOD_ROOT_SECRET", secret)
    with pytest.raises(ValueError) as failure:
        load_server_app_config(".env")
    assert str(failure.value) == (
        "UMBOD_ROOT_SECRET is required and must not be blank to start API or MCP servers. "
        "Configure a persistent secret before starting the server."
    )


def test_server_loader_uses_persistent_root_for_stable_derived_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "persistent-server-test-root")
    config = load_server_app_config(".env")
    repeated = load_server_app_config(".env")
    assert config == load_app_config(".env")
    assert config.connector_security.configuration_secret
    assert config.connector_security.configuration_secret == repeated.connector_security.configuration_secret
    assert config.connector_security.configuration_secret != config.connector_security.approval_state_key


def test_server_loader_resolves_dotenv_and_environment_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / "server.env"
    dotenv.write_text("UMBOD_ROOT_SECRET=dotenv-persistent-test-root\n", encoding="utf-8")
    from_file = load_server_app_config(str(dotenv))
    assert from_file == load_app_config(str(dotenv))
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "environment-persistent-test-root")
    from_environment = load_server_app_config(str(dotenv))
    assert from_environment == load_app_config(str(dotenv))
    assert from_file.connector_security.configuration_secret != from_environment.connector_security.configuration_secret
    for blank in ("", " ", "\t\r\n"):
        monkeypatch.setenv("UMBOD_ROOT_SECRET", blank)
        with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
            load_server_app_config(str(dotenv))


def test_missing_dotenv_root_error_does_not_disclose_other_dotenv_secrets(tmp_path: Path) -> None:
    dotenv = tmp_path / "provider.env"
    dotenv.write_text("UMBOD_OIDC_CLIENT_SECRET=private-provider-test-secret\nUMBOD_REST_PORT=invalid\n", encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        load_server_app_config(str(dotenv))
    assert str(failure.value) == (
        "UMBOD_ROOT_SECRET is required and must not be blank to start API or MCP servers. "
        "Configure a persistent secret before starting the server."
    )
    assert failure.value.__suppress_context__ is True


@pytest.mark.parametrize("port_setting", ["UMBOD_REST_PORT", "UMBOD_MCP_PORT"])
def test_valid_root_preserves_unrelated_port_validation_without_disclosing_root(
    monkeypatch: pytest.MonkeyPatch, port_setting: str
) -> None:
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "private-root-validation-test-secret")
    monkeypatch.setenv(port_setting, "invalid")
    with pytest.raises(ValidationError) as failure:
        load_server_app_config(".env")
    assert port_setting in str(failure.value)
    assert "private-root-validation-test-secret" not in str(failure.value)
    assert "UMBOD_ROOT_SECRET is required" not in str(failure.value)


def test_server_loader_rechecks_full_operator_root_when_source_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "persistent-initial-test-root")
    operator_load = Mock(wraps=OperatorSettings)

    def change_source_after_preflight(_env_file: str) -> ServerRootSettings:
        settings = ServerRootSettings(_env_file=_env_file)
        monkeypatch.setenv("UMBOD_ROOT_SECRET", " ")
        return settings

    monkeypatch.setattr(derive, "ServerRootSettings", change_source_after_preflight)
    monkeypatch.setattr(derive, "OperatorSettings", operator_load)
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET is required"):
        load_server_app_config(".env")
    operator_load.assert_called_once_with(_env_file=".env")


def test_generic_local_loader_still_accepts_secretless_configuration() -> None:
    config = load_app_config(".env")
    assert config.runtime.profile == "local"


def test_generic_production_loader_retains_root_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", "production")
    monkeypatch.setenv("UMBOD_AUTH", "google")
    monkeypatch.setenv("UMBOD_OIDC_CLIENT_ID", "production-test-client")
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
        load_app_config(".env")
