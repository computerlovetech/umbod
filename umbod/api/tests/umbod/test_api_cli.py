from typing import Any

from pytest import MonkeyPatch

from umbod.cli.api import ServeCommand
from umbod.config import AppConfig, RestConfig


def _run(
    monkeypatch: MonkeyPatch, configured_port: int, cli_port: int | None = None
) -> dict[str, Any]:
    invocation: dict[str, Any] = {}
    monkeypatch.setattr(
        "umbod.cli.api.load_app_config",
        lambda env_file: AppConfig(rest=RestConfig(port=configured_port)),
    )
    monkeypatch.setattr(
        "umbod.cli.api.uvicorn.run",
        lambda *args, **kwargs: invocation.update(kwargs),
    )

    ServeCommand()(host="0.0.0.0", port=cli_port, reload=False)
    return invocation


def test_serve_uses_configured_rest_traffic_port(monkeypatch: MonkeyPatch) -> None:
    invocation = _run(monkeypatch, configured_port=9100)

    assert invocation["port"] == 9100


def test_serve_preserves_explicit_cli_port(monkeypatch: MonkeyPatch) -> None:
    invocation = _run(monkeypatch, configured_port=9100, cli_port=9200)

    assert invocation["port"] == 9200


def test_serve_ignores_legacy_platform_port_override(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9300")

    invocation = _run(monkeypatch, configured_port=9100, cli_port=9200)

    assert invocation["port"] == 9200
