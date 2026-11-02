from pathlib import Path

import pytest

from umbod.config.app import AppConfig
from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
from umbod.infrastructure.telemetry import create_configured_analytics_runtime


@pytest.mark.asyncio
async def test_disabled_config_creates_no_files(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    config = AppConfig.model_validate(
        {
            "telemetry_analytics": {"enabled": False, "sqlite_path": str(path)},
        }
    )
    runtime = create_configured_analytics_runtime(config)
    await runtime.ensure_ready()
    await runtime.shutdown()
    assert not path.exists()


@pytest.mark.asyncio
async def test_enabled_config_uses_independent_database(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    application = tmp_path / "application.sqlite3"
    config = AppConfig.model_validate(
        {
            "telemetry_analytics": {"enabled": True, "sqlite_path": str(path)},
            "connector_store": {"type": "sqlite", "sqlite_path": str(application)},
        }
    )
    runtime = create_configured_analytics_runtime(config)
    await runtime.ensure_ready()
    await runtime.shutdown()
    assert path.exists()
    assert not application.exists()


def test_enabled_config_rejects_unsafe_application_uri(tmp_path: Path) -> None:
    config = AppConfig.model_validate(
        {
            "telemetry_analytics": {
                "enabled": True,
                "sqlite_path": str(tmp_path / "analytics.sqlite3"),
            },
            "connector_store": {
                "type": "sqlite",
                "sqlite_path": "file:application.sqlite3?mode=rwc",
            },
        }
    )
    with pytest.raises(ValueError, match="unsafe"):
        create_configured_analytics_runtime(config)


@pytest.mark.asyncio
async def test_runtime_rechecks_application_alias_before_readiness(
    tmp_path: Path,
) -> None:
    from umbod.infrastructure.telemetry import create_sqlite_analytics_runtime

    application = tmp_path / "application.sqlite3"
    application.touch()
    analytics = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(analytics, (application,))
    analytics.hardlink_to(application)
    with pytest.raises(TelemetryAnalyticsUnavailable):
        await runtime.ensure_ready()
    await runtime.shutdown()
    assert application.read_bytes() == b""
