import json
import subprocess

import pytest

from tests.deployment.test_proxy_compose import authentication_compose_configuration
from tests.deployment.test_static_frontend import FRONTEND_ROOT
from umbod.config import defaults


@pytest.mark.parametrize("maximum_bytes", [1, 4096, 2097152, 9007199254740991])
def test_compose_preview_limit_is_shared_by_backend_and_browser(maximum_bytes: int) -> None:
    settings = {"UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES": str(maximum_bytes)}
    configuration = authentication_compose_configuration(settings)
    for service in ("api", "mcp", "frontend"):
        assert configuration["services"][service]["environment"]["UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES"] == str(maximum_bytes)


def test_compose_default_preview_limit_matches_backend_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES", raising=False)
    configuration = authentication_compose_configuration()
    for service in ("api", "mcp", "frontend"):
        assert configuration["services"][service]["environment"]["UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES"] == str(defaults.FILESYSTEM_PREVIEW_MAX_BYTES)


@pytest.mark.parametrize("maximum_bytes", [1, 4096, 2097152, 9007199254740991])
def test_frontend_runtime_configuration_exposes_configured_numeric_preview_limit(maximum_bytes: int) -> None:
    result = subprocess.run(
        ["/bin/sh", str(FRONTEND_ROOT / "deployment" / "generate-config.sh")],
        env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES": str(maximum_bytes)},
        check=True, capture_output=True, text=True,
    )
    configuration = json.loads(result.stdout)
    assert configuration["filesystemPreviewMaxBytes"] == maximum_bytes
    assert type(configuration["filesystemPreviewMaxBytes"]) is int


@pytest.mark.parametrize("maximum_bytes", ["", "0", "01", "-1", "1.5", "1.0", "1e3", "true", "invalid", "9007199254740992"])
def test_frontend_startup_rejects_invalid_preview_limits(maximum_bytes: str) -> None:
    result = subprocess.run(
        ["/bin/sh", str(FRONTEND_ROOT / "deployment" / "generate-config.sh")],
        env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES": maximum_bytes},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "preview" in result.stderr.lower()
