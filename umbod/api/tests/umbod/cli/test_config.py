import json
from typing import Any

import pytest

from umbod.cli.config import ShowCommand
from umbod.config import AppConfig, RuntimeConfig


def _run_show(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    advanced: bool,
) -> dict[str, Any]:
    config = AppConfig(
        runtime=RuntimeConfig(app_name="cli-instance"),
        oidc={"client_secret": "cli-secret"},
    )
    monkeypatch.setattr("umbod.cli.config.load_app_config", lambda env_file: config)

    ShowCommand()(advanced=advanced)

    return json.loads(capsys.readouterr().out)


def test_config_show_summary_remains_backward_compatible(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_show(monkeypatch, capsys, advanced=False)

    assert list(result) == [
        "admin_authentication",
        "connector_store",
        "endpoints",
        "mcp",
        "oidc",
        "runtime",
    ]
    assert result["runtime"]["app_name"] == "cli-instance"
    assert result["mcp"] == {
        "auth_mode": "single_test_user",
        "connector_tool_exposure_mode": "flat",
    }
    assert result["oidc"] == {"provider": "google"}


def test_config_show_advanced_uses_public_allow_list(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_show(monkeypatch, capsys, advanced=True)
    serialized = json.dumps(result)

    assert result["runtime"]["app_name"] == "cli-instance"
    assert "client_secret" not in serialized
    assert "cli-secret" not in serialized
    assert "***" not in serialized
