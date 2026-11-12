import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from umbod.config import OperatorSettings, load_app_config_without_env_file
from umbod.config.app import PersonalUsageConfig


def test_personal_usage_defaults_are_bounded_operational_defaults() -> None:
    assert PersonalUsageConfig().model_dump() == {
        "enabled": True, "queue_capacity": 4096, "max_record_bytes": 2048,
        "batch_size": 128, "flush_interval_seconds": 1.0, "write_timeout_seconds": 5.0,
        "max_retries": 3, "shutdown_timeout_seconds": 10.0, "retention_days": 90,
    }


def test_personal_usage_environment_maps_all_fields_into_app_config(monkeypatch: MonkeyPatch) -> None:
    values = {
        "enabled": "false", "queue_capacity": "512", "max_record_bytes": "4096",
        "batch_size": "64", "flush_interval_seconds": "2.5", "write_timeout_seconds": "8",
        "max_retries": "2", "shutdown_timeout_seconds": "20", "retention_days": "30",
    }
    for name, value in values.items():
        monkeypatch.setenv(f"UMBOD_PERSONAL_USAGE_{name.upper()}", value)
    expected = PersonalUsageConfig.model_validate(values)
    operator = OperatorSettings(_env_file=None)
    config = load_app_config_without_env_file()
    assert config.personal_usage == expected
    for name, value in expected.model_dump().items():
        assert getattr(operator, f"personal_usage_{name}") == value


@pytest.mark.parametrize("field,value", [
    ("queue_capacity", 0), ("queue_capacity", 65537),
    ("max_record_bytes", 0), ("max_record_bytes", 65537),
    ("batch_size", 0), ("batch_size", 1025),
    ("flush_interval_seconds", 0), ("flush_interval_seconds", float("inf")),
    ("flush_interval_seconds", float("nan")), ("write_timeout_seconds", 61),
    ("max_retries", -1), ("max_retries", 6),
    ("shutdown_timeout_seconds", 0), ("shutdown_timeout_seconds", float("inf")),
    ("retention_days", 0), ("retention_days", 3651),
])
def test_personal_usage_rejects_unbounded_values(field: str, value: int | float) -> None:
    with pytest.raises(ValidationError):
        PersonalUsageConfig.model_validate({field: value})


def test_personal_usage_batch_cannot_exceed_queue_capacity(monkeypatch: MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="batch size cannot exceed queue capacity"):
        PersonalUsageConfig(queue_capacity=64, batch_size=128)
    monkeypatch.setenv("UMBOD_PERSONAL_USAGE_QUEUE_CAPACITY", "64")
    with pytest.raises(ValidationError, match="batch size cannot exceed queue capacity"):
        OperatorSettings(_env_file=None)
