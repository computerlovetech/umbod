from typing import Any

from pytest import MonkeyPatch

from umbod.cli.mcp import ServeCommand
from umbod.config import AppConfig, McpConfig


def _run(
    monkeypatch: MonkeyPatch, configured_port: int, cli_port: int | None = None
) -> dict[str, Any]:
    invocation: dict[str, Any] = {}
    monkeypatch.setattr(
        "umbod.cli.mcp.load_app_config",
        lambda env_file: AppConfig(mcp=McpConfig(port=configured_port)),
    )
    monkeypatch.setattr(
        "umbod.cli.mcp.uvicorn.run",
        lambda *args, **kwargs: invocation.update({"args": args, **kwargs}),
    )

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

    assert invocation["args"] == ("umbod.mcp.main:app",)
