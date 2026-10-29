import json
import os
from pathlib import Path
from typing import Any

import pytest

from umbod.cli.config import ShowCommand
from umbod.config import load_app_config


@pytest.fixture(autouse=True)
def isolated_operator_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name in os.environ:
        if name.startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "dev")
    monkeypatch.setenv("UMBOD_APP_NAME", "cli-instance")


def _run_show(
    capsys: pytest.CaptureFixture[str],
    advanced: bool,
) -> dict[str, Any]:
    ShowCommand()(advanced=advanced)

    return json.loads(capsys.readouterr().out)


def test_config_show_summary_remains_backward_compatible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_show(capsys, advanced=False)

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
    monkeypatch.setenv("UMBOD_AUTH", "google")
    monkeypatch.setenv("UMBOD_OIDC_CLIENT_ID", "cli-client")
    monkeypatch.setenv("UMBOD_OIDC_CLIENT_SECRET", "cli-secret")
    assert load_app_config(".env").oidc.client_secret == "cli-secret"

    result = _run_show(capsys, advanced=True)
    serialized = json.dumps(result)

    assert result["runtime"]["app_name"] == "cli-instance"
    assert "client_secret" not in serialized
    assert "cli-secret" not in serialized
    assert "***" not in serialized
