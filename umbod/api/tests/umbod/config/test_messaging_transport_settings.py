import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from umbod.config import OperatorSettings, load_app_config_without_env_file


def test_messaging_transport_defaults_to_http() -> None:
    assert OperatorSettings(_env_file=None).mcp_messaging_transport == "http"


def test_messaging_transport_reads_sql_from_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_MCP_MESSAGING_TRANSPORT", "sql")

    operator = OperatorSettings(_env_file=None)
    config = load_app_config_without_env_file()

    assert operator.mcp_messaging_transport == "sql"
    assert config.mcp.messaging_transport == "sql"


def test_messaging_transport_rejects_invalid_environment_value(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_MCP_MESSAGING_TRANSPORT", "invalid")

    with pytest.raises(ValidationError):
        OperatorSettings(_env_file=None)
