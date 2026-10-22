from pathlib import Path
from typing import Optional
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from umbod.cli import api, mcp
from umbod.cli.main import app


@pytest.mark.parametrize("invalid_setting", [None, "UMBOD_REST_PORT", "UMBOD_MCP_PORT", "UMBOD_OTLP_ENABLED"])
@pytest.mark.parametrize("service", ["api", "mcp"])
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("secret", [None, "", " \t\n"])
def test_serve_rejects_blank_root_before_logging_or_listener_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service: str,
    reload: bool,
    secret: Optional[str],
    invalid_setting: Optional[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UMBOD_ROOT_SECRET", raising=False)
    if secret is not None:
        monkeypatch.setenv("UMBOD_ROOT_SECRET", secret)
    if invalid_setting is not None:
        monkeypatch.setenv(invalid_setting, "invalid")
    module = api if service == "api" else mcp
    run = Mock()
    configure = Mock()
    bind = Mock()
    metrics = Mock()
    monkeypatch.setattr(module.uvicorn, "run", run)
    monkeypatch.setattr(module, "configure_logging", configure)
    monkeypatch.setattr("socket.socket.bind", bind)
    monkeypatch.setattr("umbod.rest.metrics.RestMetricsHttpServer.start", metrics)
    monkeypatch.setattr("umbod.mcp.metrics.http_server.McpMetricsHttpServer.start", metrics)
    arguments = [service, "serve", "--reload"] if reload else [service, "serve"]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 1
    assert "UMBOD_ROOT_SECRET is required and must not be blank" in result.stderr
    assert "Traceback" not in result.output
    assert "running" not in result.output.lower()
    run.assert_not_called()
    configure.assert_not_called()
    bind.assert_not_called()
    metrics.assert_not_called()


@pytest.mark.parametrize("service,port_setting", [("api", "UMBOD_REST_PORT"), ("mcp", "UMBOD_MCP_PORT")])
def test_valid_root_reports_unrelated_port_error_without_disclosing_root_or_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, service: str, port_setting: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "private-cli-validation-test-root")
    monkeypatch.setenv(port_setting, "invalid")
    run = Mock()
    bind = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    monkeypatch.setattr("socket.socket.bind", bind)
    result = CliRunner().invoke(app, [service, "serve", "--reload"])
    assert result.exit_code == 1
    assert port_setting in result.stderr
    assert "private-cli-validation-test-root" not in result.output
    assert "UMBOD_ROOT_SECRET is required" not in result.output
    assert "Traceback" not in result.output
    run.assert_not_called()
    bind.assert_not_called()


@pytest.mark.parametrize("command", ["show", "validate"])
def test_configuration_utility_remains_available_without_local_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UMBOD_ROOT_SECRET", raising=False)
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "dev")
    result = CliRunner().invoke(app, ["config", command])
    assert result.exit_code == 0, result.output
