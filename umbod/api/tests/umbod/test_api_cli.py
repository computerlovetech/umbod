import os
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from umbod.cli.api import ServeCommand


@pytest.fixture(autouse=True)
def isolated_server_environment(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    for name in tuple(os.environ):
        if name.upper().startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "testvalidsecret")
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "dev")


def _run(
    monkeypatch: MonkeyPatch, configured_port: int, cli_port: int | None = None
) -> dict[str, Any]:
    invocation: dict[str, Any] = {}
    monkeypatch.setenv("UMBOD_REST_PORT", str(configured_port))

    def record_invocation(*args: object, **kwargs: object) -> None:
        invocation.update(kwargs)

    monkeypatch.setattr("umbod.cli.api.uvicorn.run", record_invocation)

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
