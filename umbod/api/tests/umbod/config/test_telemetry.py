import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from umbod.config import load_app_config
from umbod.config.app import OtlpReceiverConfig, RuntimeConfig, TelemetryAnalyticsConfig
from umbod.config.telemetry import TelemetryAppConfig, load_telemetry_app_config


@pytest.fixture(autouse=True)
def isolated_telemetry_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in tuple(os.environ):
        if name.upper().startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


def test_receiver_configuration_has_no_deployment_selector() -> None:
    settings = load_app_config(".env")
    assert set(type(settings.otlp_receiver).model_fields) == {
        "host", "port", "enabled", "bearer_token", "allow_unauthenticated", "max_request_bytes",
    }


def test_telemetry_defaults_only_contain_telemetry_settings() -> None:
    config = load_telemetry_app_config(".env")

    assert set(type(config).model_fields) == {
        "runtime", "otlp_receiver", "telemetry_analytics"
    }
    assert config.runtime.profile == "local"
    assert config.otlp_receiver.host == "0.0.0.0"
    assert config.otlp_receiver.port == 4318
    assert not config.otlp_receiver.enabled
    assert not config.telemetry_analytics.enabled


def test_telemetry_production_ignores_unrelated_invalid_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "UMBOD_PROFILE": "production",
        "UMBOD_OTLP_ENABLED": "true",
        "UMBOD_OTLP_BEARER_TOKEN": "receiver-token",
        "UMBOD_AUTH": "invalid",
        "UMBOD_ROOT_SECRET": "",
        "UMBOD_OIDC_REQUIRED_SCOPES": "invalid-json",
        "UMBOD_REST_PORT": "not-a-port",
        "UMBOD_CONNECTOR_STORE": "invalid",
    }.items():
        monkeypatch.setenv(name, value)

    config = load_telemetry_app_config(".env")

    assert config.runtime.profile == "production"
    assert config.otlp_receiver.bearer_token == "receiver-token"


def test_telemetry_loads_dedicated_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / "telemetry.env"
    env_file.write_text(
        "UMBOD_APP_NAME=receiver\nUMBOD_LOG_LEVEL=debug\n"
        "UMBOD_OTLP_ENABLED=true\nUMBOD_OTLP_ALLOW_UNAUTHENTICATED=true\n"
        "UMBOD_OTLP_HOST=127.0.0.1\nUMBOD_OTLP_PORT=9438\n"
        "UMBOD_OTLP_MAX_REQUEST_BYTES=2048\n"
        "UMBOD_TELEMETRY_ANALYTICS_ENABLED=true\n"
        "UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH=/tmp/analytics.sqlite3\n"
        "UMBOD_REST_PORT=invalid\n",
        encoding="utf-8",
    )

    config = load_telemetry_app_config(str(env_file))

    assert config.runtime.app_name == "receiver"
    assert config.runtime.log_level == "debug"
    assert config.otlp_receiver.host == "127.0.0.1"
    assert config.otlp_receiver.port == 9438
    assert config.otlp_receiver.max_request_bytes == 2048
    assert config.otlp_receiver.allow_unauthenticated
    assert config.telemetry_analytics.enabled
    assert config.telemetry_analytics.sqlite_path == "/tmp/analytics.sqlite3"


@pytest.mark.parametrize(
    "name,value",
    [
        ("UMBOD_PROFILE", "staging"),
        ("UMBOD_OTLP_PORT", "0"),
        ("UMBOD_OTLP_PORT", "65536"),
        ("UMBOD_OTLP_PORT", "invalid"),
        ("UMBOD_OTLP_MAX_REQUEST_BYTES", "0"),
        ("UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH", ":memory:"),
    ],
)
def test_telemetry_rejects_invalid_settings(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        load_telemetry_app_config(".env")


@pytest.mark.parametrize("token", ["", "  ", "secret token", "secret\ttoken"])
def test_enabled_receiver_rejects_missing_or_whitespace_token(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    monkeypatch.setenv("UMBOD_OTLP_ENABLED", "true")
    monkeypatch.setenv("UMBOD_OTLP_BEARER_TOKEN", token)

    with pytest.raises(ValidationError):
        load_telemetry_app_config(".env")


def test_telemetry_model_rejects_unauthenticated_production_receiver() -> None:
    with pytest.raises(ValidationError, match="requires UMBOD_PROFILE=local"):
        TelemetryAppConfig(
            runtime=RuntimeConfig(profile="production"),
            otlp_receiver=OtlpReceiverConfig(allow_unauthenticated=True),
            telemetry_analytics=TelemetryAnalyticsConfig(),
        )


def test_telemetry_model_rejects_unknown_profile() -> None:
    with pytest.raises(ValidationError, match="local or production"):
        TelemetryAppConfig(
            runtime=RuntimeConfig(profile="staging"),
            otlp_receiver=OtlpReceiverConfig(),
            telemetry_analytics=TelemetryAnalyticsConfig(),
        )
