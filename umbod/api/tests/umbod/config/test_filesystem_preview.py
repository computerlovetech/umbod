import pytest
from pydantic import ValidationError

from umbod.config import AppConfig, FilesystemRuntimeConfig, OperatorSettings, build_app_config, inspect_app_config


def test_preview_limit_defaults_to_one_mebibyte(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES", raising=False)
    assert AppConfig().filesystem.preview_max_bytes == 1_048_576
    assert build_app_config(OperatorSettings(_env_file=None)).filesystem.preview_max_bytes == 1_048_576


@pytest.mark.parametrize("limit", [1, 37, 9_007_199_254_740_991])
def test_preview_limit_environment_reaches_runtime_and_inspection(
    monkeypatch: pytest.MonkeyPatch, limit: int,
) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES", str(limit))
    config = build_app_config(OperatorSettings(_env_file=None))
    assert config.filesystem.preview_max_bytes == limit
    entries = {
        entry.variable: entry
        for group in inspect_app_config(config).groups
        for entry in group.entries
    }
    assert entries["UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES"].value == limit
    assert entries["UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES"].type == "integer"


@pytest.mark.parametrize("value", ["0", "-1", "9007199254740992", "1.5", "1.0", "NaN", "abc", "", "1e3", "01", "+1", " 1", "1 "])
def test_preview_limit_rejects_invalid_environment(
    monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    monkeypatch.setenv("UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES", value)
    with pytest.raises(ValidationError, match="filesystem_preview_max_bytes"):
        OperatorSettings(_env_file=None)


@pytest.mark.parametrize("value", [0, -1, 9_007_199_254_740_992, 1.5, 1.0, True])
def test_operator_preview_limit_rejects_invalid_typed_values(value: object) -> None:
    with pytest.raises(ValidationError, match="filesystem_preview_max_bytes"):
        OperatorSettings(_env_file=None, filesystem_preview_max_bytes=value)


@pytest.mark.parametrize("value", [0, -1, 9_007_199_254_740_992, 1.5, 1.0, True, "37"])
def test_runtime_preview_limit_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValidationError, match="preview_max_bytes"):
        FilesystemRuntimeConfig(preview_max_bytes=value)
