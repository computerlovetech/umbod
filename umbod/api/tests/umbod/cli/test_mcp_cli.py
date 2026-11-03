import os
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch, fixture

from umbod.cli.mcp import ServeCommand


@fixture(autouse=True)
def isolated_operator_environment(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    for name in tuple(os.environ):
        if name.upper().startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "mcp-cli-test-root-secret")
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "dev")


def _run(
    monkeypatch: MonkeyPatch, configured_port: int, cli_port: int | None = None
) -> dict[str, Any]:
    invocation: dict[str, Any] = {}
    monkeypatch.setenv("UMBOD_MCP_PORT", str(configured_port))

    def record_server_invocation(*args: object, **kwargs: object) -> None:
        invocation.update({"args": args, **kwargs})

    monkeypatch.setattr("umbod.cli.mcp.uvicorn.run", record_server_invocation)

    ServeCommand()(host="0.0.0.0", port=cli_port, reload=False)
    return invocation


def test_serve_uses_configured_mcp_traffic_port(monkeypatch: MonkeyPatch) -> None:
    invocation = _run(monkeypatch, configured_port=9100)

    assert invocation["port"] == 9100


def test_serve_preserves_explicit_cli_port(monkeypatch: MonkeyPatch) -> None:
    invocation = _run(monkeypatch, configured_port=9100, cli_port=9200)

    assert invocation["port"] == 9200


def test_serve_starts_the_mcp_application(monkeypatch: MonkeyPatch) -> None:
    invocation = _run(monkeypatch, configured_port=9100)

    assert invocation["args"] == ("umbod.hosting.mcp_service:app",)
