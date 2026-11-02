import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from umbod.config import (
    AppConfig,
    OperatorSettings,
    TelemetryAnalyticsConfig,
    build_app_config,
    inspect_app_config,
    safe_app_config_dump,
)


@pytest.fixture(autouse=True)
def isolated_operator_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in os.environ:
        if name.startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


def test_analytics_defaults_are_disabled_with_independent_disk_path() -> None:
    operator = OperatorSettings()
    config = build_app_config(operator)

    assert operator.telemetry_analytics_enabled is False
    assert operator.telemetry_analytics_sqlite_path == ".data/analytics.sqlite3"
    assert config.telemetry_analytics == TelemetryAnalyticsConfig()
    assert AppConfig().telemetry_analytics.model_dump() == {
        "enabled": False,
        "sqlite_path": ".data/analytics.sqlite3",
    }


@pytest.mark.parametrize("enabled", [True, False])
def test_analytics_environment_overrides_are_assembled(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setenv("UMBOD_TELEMETRY_ANALYTICS_ENABLED", str(enabled).lower())
    monkeypatch.setenv("UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH", "metrics/analytics.sqlite3")

    config = build_app_config(OperatorSettings())

    assert config.telemetry_analytics.enabled is enabled
    assert config.telemetry_analytics.sqlite_path == "metrics/analytics.sqlite3"


def test_analytics_path_does_not_inherit_application_path_or_data_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_DATA_DIR", "/custom/application")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE_SQLITE_PATH", "/other/application.sqlite3")

    config = build_app_config(OperatorSettings())

    assert config.connector_store.sqlite_path == "/other/application.sqlite3"
    assert config.telemetry_analytics.sqlite_path == ".data/analytics.sqlite3"


@pytest.mark.parametrize(
    "path", ["", " ", "\t\n", ":memory:", "file:analytics.sqlite3", "file::memory:?cache=shared", "bad\x00path"]
)
def test_analytics_rejects_invalid_disk_paths_in_runtime_and_operator_settings(path: str) -> None:
    with pytest.raises(ValidationError, match="on-disk SQLite path"):
        TelemetryAnalyticsConfig(sqlite_path=path)
    with pytest.raises(ValidationError, match="on-disk SQLite path"):
        OperatorSettings(telemetry_analytics_sqlite_path=path)


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_enabled_analytics_rejects_canonical_application_paths(
    tmp_path: Path, suffix: str
) -> None:
    application_path = tmp_path / "application.sqlite3"
    analytics_path = tmp_path / "unused" / ".." / f"application.sqlite3{suffix}"

    with pytest.raises(ValidationError, match="separate SQLite file"):
        AppConfig(
            connector_store={"type": "sqlite", "sqlite_path": str(application_path)},
            telemetry_analytics={"enabled": True, "sqlite_path": str(analytics_path)},
        )


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_enabled_analytics_rejects_existing_application_file_aliases(
    tmp_path: Path, suffix: str, link_kind: str
) -> None:
    application_path = tmp_path / "application.sqlite3"
    protected_path = Path(f"{application_path}{suffix}")
    protected_path.touch()
    analytics_path = tmp_path / "analytics.sqlite3"
    if link_kind == "symlink":
        analytics_path.symlink_to(protected_path)
    else:
        analytics_path.hardlink_to(protected_path)

    with pytest.raises(ValidationError, match="separate SQLite file"):
        AppConfig(
            connector_store={"type": "sqlite", "sqlite_path": str(application_path)},
            telemetry_analytics={"enabled": True, "sqlite_path": str(analytics_path)},
        )


def test_enabled_analytics_rejects_sidecar_of_resolved_application_symlink(tmp_path: Path) -> None:
    application_path = tmp_path / "application.sqlite3"
    application_path.symlink_to(tmp_path / "actual.sqlite3")

    with pytest.raises(ValidationError, match="separate SQLite file"):
        AppConfig(
            connector_store={"type": "sqlite", "sqlite_path": str(application_path)},
            telemetry_analytics={
                "enabled": True,
                "sqlite_path": str(tmp_path / "actual.sqlite3-wal"),
            },
        )


def test_environment_configuration_rejects_application_database_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "sqlite")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE_SQLITE_PATH", "application.sqlite3")
    monkeypatch.setenv("UMBOD_TELEMETRY_ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH", "./application.sqlite3")

    with pytest.raises(ValidationError, match="separate SQLite file"):
        build_app_config(OperatorSettings())


def test_disabled_analytics_does_not_require_file_separation() -> None:
    config = AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": "application.sqlite3"},
        telemetry_analytics={"enabled": False, "sqlite_path": "application.sqlite3"},
    )

    assert config.telemetry_analytics.enabled is False


def test_enabled_analytics_is_independent_of_inmemory_application_store() -> None:
    config = AppConfig(telemetry_analytics={"enabled": True})

    assert config.connector_store.type == "inmemory"
    assert config.telemetry_analytics.enabled is True


def test_configuration_validation_does_not_create_database_files(tmp_path: Path) -> None:
    application_path = tmp_path / "application" / "store.sqlite3"
    analytics_path = tmp_path / "analytics" / "store.sqlite3"

    AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": str(application_path)},
        telemetry_analytics={"enabled": True, "sqlite_path": str(analytics_path)},
    )

    assert list(tmp_path.iterdir()) == []


def test_safe_inspection_exposes_separate_analytics_group_without_ingestion_secret() -> None:
    config = AppConfig(
        telemetry_analytics={"enabled": True, "sqlite_path": "analytics.sqlite3"},
        otlp_receiver={"bearer_token": "private-ingestion-token"},
    )

    inspection = inspect_app_config(config)
    group = next(group for group in inspection.groups if group.id == "telemetry_analytics")

    assert {entry.variable: entry.value for entry in group.entries} == {
        "UMBOD_TELEMETRY_ANALYTICS_ENABLED": True,
        "UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH": "analytics.sqlite3",
    }
    assert safe_app_config_dump(config)["telemetry_analytics"] == {
        "enabled": True,
        "sqlite_path": "analytics.sqlite3",
    }
    assert "private-ingestion-token" not in inspection.model_dump_json()
    assert "bearer_token" not in safe_app_config_dump(config)["otlp_receiver"]
