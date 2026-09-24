import pytest
from pydantic import ValidationError

from umbod.config.app import EndpointsConfig
from umbod.config import OperatorSettings, build_app_config


def test_downstream_oauth_is_opt_in(monkeypatch):
    monkeypatch.delenv("UMBOD_MCP_DOWNSTREAM_OAUTH_ENABLED", raising=False)
    disabled = build_app_config(OperatorSettings(_env_file=None))
    assert disabled.mcp.downstream_oauth_enabled is False
    monkeypatch.setenv("UMBOD_MCP_DOWNSTREAM_OAUTH_ENABLED", "true")
    enabled = build_app_config(OperatorSettings(_env_file=None))
    assert enabled.mcp.downstream_oauth_enabled is True
    assert enabled.oidc == disabled.oidc
    assert enabled.admin_authentication == disabled.admin_authentication
    assert enabled.mcp.auth_mode == disabled.mcp.auth_mode
    assert enabled.oauth_storage == disabled.oauth_storage


@pytest.mark.parametrize(
    "origin",
    [
        "http://provider.example",
        "https://user@provider.example",
        "https://provider.example/path",
        "https://provider.example?secret=value",
        "https://provider.example#fragment",
    ],
)
def test_public_api_origin_rejects_unsafe_callback_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        EndpointsConfig(api_base_url=origin)


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("https://agent.example/", "https://agent.example"),
        ("http://localhost:8010", "http://localhost:8010"),
    ],
)
def test_public_api_origin_accepts_https_and_loopback_development(
    origin: str, expected: str
) -> None:
    assert EndpointsConfig(api_base_url=origin).api_base_url == expected
