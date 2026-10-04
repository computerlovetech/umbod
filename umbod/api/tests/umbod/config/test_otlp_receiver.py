import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from umbod.config import (
    OperatorSettings,
    build_app_config,
    redact_app_config,
    safe_app_config_dump,
)


def test_receiver_is_disabled_and_protected_by_default() -> None:
    config = build_app_config(OperatorSettings(_env_file=None))
    assert config.otlp_receiver.enabled is False
    assert config.otlp_receiver.allow_unauthenticated is False
    assert config.otlp_receiver.max_request_bytes == 10 * 1024 * 1024


def test_receiver_reads_operator_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_OTLP_ENABLED", "true")
    monkeypatch.setenv("UMBOD_OTLP_BEARER_TOKEN", "dedicated-ingestion-token")
    monkeypatch.setenv("UMBOD_OTLP_MAX_REQUEST_BYTES", "4096")
    config = build_app_config(OperatorSettings(_env_file=None))
    assert config.otlp_receiver.enabled is True
    assert config.otlp_receiver.bearer_token == "dedicated-ingestion-token"
    assert config.otlp_receiver.max_request_bytes == 4096


@pytest.mark.parametrize("token", ["", " ", "token with spaces"])
def test_enabled_receiver_requires_usable_dedicated_token(token: str) -> None:
    operator = OperatorSettings(
        _env_file=None, otlp_enabled=True, otlp_bearer_token=token
    )
    with pytest.raises(ValueError, match="UMBOD_OTLP_BEARER_TOKEN"):
        build_app_config(operator)


def test_local_unauthenticated_ingestion_requires_explicit_opt_in() -> None:
    config = build_app_config(
        OperatorSettings(
            _env_file=None, otlp_enabled=True, otlp_allow_unauthenticated=True
        )
    )
    assert config.otlp_receiver.allow_unauthenticated is True


def test_production_rejects_unauthenticated_ingestion_before_oidc_validation() -> None:
    operator = OperatorSettings(
        _env_file=None,
        profile="production",
        auth="google",
        root_secret="production-root",
        otlp_allow_unauthenticated=True,
    )
    with pytest.raises(ValueError, match="only allowed with UMBOD_PROFILE=local"):
        build_app_config(operator)


@pytest.mark.parametrize("limit", [0, -1])
def test_request_size_limit_must_be_positive(limit: int) -> None:
    with pytest.raises(ValidationError):
        OperatorSettings(_env_file=None, otlp_max_request_bytes=limit)


def test_receiver_token_is_redacted_and_excluded_from_inspection() -> None:
    operator = OperatorSettings(
        _env_file=None, otlp_enabled=True, otlp_bearer_token="dedicated-ingestion-token"
    )
    config = build_app_config(operator)
    assert redact_app_config(config)["otlp_receiver"]["bearer_token"] == "***"
    assert "bearer_token" not in safe_app_config_dump(config)["otlp_receiver"]
    assert "dedicated-ingestion-token" not in repr(operator)
    assert "dedicated-ingestion-token" not in repr(config)
