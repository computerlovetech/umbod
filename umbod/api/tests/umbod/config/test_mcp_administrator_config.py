import os
from typing import Literal

import pytest

from umbod.config import (
    AppConfig,
    McpAdministratorConfig,
    inspect_app_config,
    load_app_config_without_env_file,
    safe_app_config_dump,
)


@pytest.fixture(autouse=True)
def isolated_operator_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in os.environ:
        if name.startswith("UMBOD_"):
            monkeypatch.delenv(name)


def test_administrator_defaults_use_separate_hosting() -> None:
    expected = {
        "hosting": "separate",
        "host": "127.0.0.1",
        "port": 8013,
        "base_url": "http://localhost:8013",
    }
    assert AppConfig().mcp_administrator.model_dump() == expected
    assert load_app_config_without_env_file().mcp_administrator.model_dump() == expected


def test_administrator_environment_maps_and_exports_dedicated_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "hosting": "separate",
        "host": "0.0.0.0",
        "port": 9013,
        "base_url": "https://administrator.example.com",
    }
    for field, value in expected.items():
        monkeypatch.setenv(f"UMBOD_MCP_ADMINISTRATOR_{field.upper()}", str(value))
    config = load_app_config_without_env_file()
    assert config.mcp_administrator.model_dump() == expected
    assert safe_app_config_dump(config)["mcp_administrator"] == expected
    inspected = {
        entry.variable: entry.value
        for group in inspect_app_config(config).groups
        for entry in group.entries
    }
    assert {
        field: inspected[f"UMBOD_MCP_ADMINISTRATOR_{field.upper()}"]
        for field in expected
    } == expected


@pytest.mark.parametrize("enabled,hosting", [(True, "shared"), (False, "shared"), (False, "separate")])
def test_inactive_dedicated_settings_do_not_require_usable_values(
    enabled: bool, hosting: Literal["shared", "separate"]
) -> None:
    config = AppConfig.model_validate({
        "mcp_administrator": {"hosting": hosting, "host": " ", "port": 0, "base_url": "invalid"},
        "feature_toggles": {"mcp_administrator_enabled": enabled},
    })
    assert config.mcp_administrator.hosting == hosting
    assert config.feature_toggles.mcp_administrator_enabled is enabled


@pytest.mark.parametrize("base_url", [
    "http://localhost:8013", "http://127.0.0.2:8013", "http://[::1]:8013",
    "https://administrator.example.com", "https://administrator.example.com/",
])
def test_separate_hosting_accepts_secure_origins(base_url: str) -> None:
    config = AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate", base_url=base_url))
    assert config.mcp_administrator.base_url == base_url


@pytest.mark.parametrize("base_url", [
    "", " ", "relative", "//example.com", "ftp://example.com", "http://example.com",
    "https://user:password@example.com", "https://example.com/path",
    "https://example.com?", "https://example.com#", "https://example.com?query=1",
    "https://example.com#fragment", "https://example.com:0", "https://example.com:65536",
    "https://example.com:invalid", "https://bad host", "https://example.com\\path",
    "https://example.com\n", "https://[invalid]",
])
def test_separate_hosting_rejects_invalid_origins(base_url: str) -> None:
    with pytest.raises(ValueError, match="MCP administrator base URL"):
        AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate", base_url=base_url))


@pytest.mark.parametrize("host", ["", " ", "\t\n"])
def test_separate_hosting_rejects_blank_bind_host(host: str) -> None:
    with pytest.raises(ValueError, match="MCP administrator host"):
        AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate", host=host))


@pytest.mark.parametrize("port", [-1, 0, 65536])
def test_separate_hosting_rejects_invalid_ports(port: int) -> None:
    with pytest.raises(ValueError, match="MCP administrator port"):
        AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate", port=port))


@pytest.mark.parametrize("port", [1, 65535])
def test_separate_hosting_accepts_port_boundaries(port: int) -> None:
    config = AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate", port=port))
    assert config.mcp_administrator.port == port


@pytest.mark.parametrize("section,field", [("rest", "port"), ("rest", "metrics_port"), ("mcp", "port"), ("mcp", "metrics_port")])
def test_separate_hosting_rejects_service_port_collisions(section: str, field: str) -> None:
    port = getattr(getattr(AppConfig(), section), field)
    with pytest.raises(ValueError, match="MCP administrator port must be distinct"):
        AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate", port=port))


@pytest.mark.parametrize("enabled", [False, True])
def test_collector_port_collision_only_applies_to_enabled_collector(enabled: bool) -> None:
    values = {
        "mcp_administrator": {"hosting": "separate", "port": 4318},
        "otlp_receiver": {"enabled": enabled},
    }
    if enabled:
        with pytest.raises(ValueError, match="MCP administrator port must be distinct"):
            AppConfig.model_validate(values)
    else:
        assert AppConfig.model_validate(values).mcp_administrator.port == 4318


def test_environment_separate_hosting_validates_active_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_MCP_ADMINISTRATOR_HOSTING", "separate")
    monkeypatch.setenv("UMBOD_MCP_ADMINISTRATOR_PORT", "0")
    with pytest.raises(ValueError, match="MCP administrator port"):
        load_app_config_without_env_file()
    monkeypatch.setenv("UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED", "false")
    config = load_app_config_without_env_file()
    assert config.mcp_administrator.port == 0
    assert config.feature_toggles.mcp_administrator_enabled is False


def test_environment_explicitly_opts_in_to_shared_hosting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_MCP_ADMINISTRATOR_HOSTING", "shared")
    assert load_app_config_without_env_file().mcp_administrator.hosting == "shared"


def test_default_administrator_listener_rejects_public_port_collision() -> None:
    with pytest.raises(ValueError, match="MCP administrator port must be distinct"):
        AppConfig.model_validate({"mcp": {"port": 8013}})


def test_unknown_hosting_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="hosting"):
        AppConfig.model_validate({"mcp_administrator": {"hosting": "unknown"}})
