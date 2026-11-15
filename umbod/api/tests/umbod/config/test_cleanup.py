import pytest
from pydantic import ValidationError

from umbod.config import OperatorSettings, build_app_config
from umbod.config.app import CleanupConfig


def test_cleanup_timeout_default_is_five_seconds() -> None:
    operator = OperatorSettings(_env_file=None)
    assert build_app_config(operator).cleanup.job_timeout_seconds == 5


def test_cleanup_timeout_reads_operator_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_CLEANUP_JOB_TIMEOUT_SECONDS", "12.5")
    operator = OperatorSettings(_env_file=None)
    assert build_app_config(operator).cleanup.job_timeout_seconds == 12.5


@pytest.mark.parametrize("value", ["0", "-1", "3601", "nan", "inf"])
def test_cleanup_timeout_rejects_invalid_operator_values(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_CLEANUP_JOB_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        OperatorSettings(_env_file=None)


@pytest.mark.parametrize("value", [0, -1, 3601, float("nan"), float("inf")])
def test_cleanup_timeout_rejects_invalid_app_config(value: float) -> None:
    with pytest.raises(ValidationError):
        CleanupConfig(job_timeout_seconds=value)
