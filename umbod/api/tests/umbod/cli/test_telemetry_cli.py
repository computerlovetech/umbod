import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from umbod.cli.main import app


@pytest.fixture(autouse=True)
def isolated_telemetry_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in tuple(os.environ):
        if name.upper().startswith("UMBOD_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def uvicorn_run(monkeypatch: pytest.MonkeyPatch) -> Mock:
    invocation = Mock()
    monkeypatch.setattr("umbod.cli.telemetry.uvicorn.run", invocation)
    monkeypatch.setattr("umbod.cli.telemetry.configure_logging", Mock())
    return invocation


def test_telemetry_registered_serve_uses_default_binding(uvicorn_run: Mock) -> None:
    result = CliRunner().invoke(app, ["telemetry", "serve"])

    assert result.exit_code == 0, result.output
    uvicorn_run.assert_called_once_with(
        "umbod.hosting.telemetry_service:create_app",
        host="0.0.0.0",
        port=4318,
        reload=False,
        log_level="info",
        log_config=None,
        factory=True,
    )


def test_telemetry_serve_uses_dedicated_config_binding(
    monkeypatch: pytest.MonkeyPatch, uvicorn_run: Mock
) -> None:
    monkeypatch.setenv("UMBOD_OTLP_HOST", "127.0.0.2")
    monkeypatch.setenv("UMBOD_OTLP_PORT", "9438")

    result = CliRunner().invoke(app, ["telemetry", "serve"])

    assert result.exit_code == 0, result.output
    assert uvicorn_run.call_args.kwargs["host"] == "127.0.0.2"
    assert uvicorn_run.call_args.kwargs["port"] == 9438


def test_telemetry_serve_preserves_explicit_cli_overrides(
    monkeypatch: pytest.MonkeyPatch, uvicorn_run: Mock
) -> None:
    monkeypatch.setenv("UMBOD_OTLP_HOST", "127.0.0.2")
    monkeypatch.setenv("UMBOD_OTLP_PORT", "9438")

    result = CliRunner().invoke(
        app,
        ["telemetry", "serve", "--host", "127.0.0.3", "--port", "9439", "--reload"],
    )

    assert result.exit_code == 0, result.output
    assert uvicorn_run.call_args.kwargs["host"] == "127.0.0.3"
    assert uvicorn_run.call_args.kwargs["port"] == 9439
    assert uvicorn_run.call_args.kwargs["reload"]


def test_telemetry_serve_production_needs_no_rest_authentication(
    monkeypatch: pytest.MonkeyPatch, uvicorn_run: Mock
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", "production")
    monkeypatch.setenv("UMBOD_OTLP_ENABLED", "true")
    monkeypatch.setenv("UMBOD_OTLP_BEARER_TOKEN", "receiver-token")
    monkeypatch.setenv("UMBOD_REST_PORT", "invalid")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "invalid")
    monkeypatch.setenv("UMBOD_AUTH", "invalid")

    result = CliRunner().invoke(app, ["telemetry", "serve"])

    assert result.exit_code == 0, result.output
    uvicorn_run.assert_called_once()


@pytest.mark.parametrize(
    "name,value",
    [
        ("UMBOD_OTLP_PORT", "0"),
        ("UMBOD_OTLP_PORT", "65536"),
        ("UMBOD_OTLP_ENABLED", "invalid"),
        ("UMBOD_OTLP_BEARER_TOKEN", "secret token"),
        ("UMBOD_OTLP_BEARER_TOKEN", ""),
        ("UMBOD_PROFILE", "staging"),
    ],
)
def test_telemetry_serve_rejects_config_without_echoing_secrets(
    monkeypatch: pytest.MonkeyPatch, uvicorn_run: Mock, name: str, value: str
) -> None:
    monkeypatch.setenv("UMBOD_OTLP_ENABLED", "true")
    monkeypatch.setenv("UMBOD_OTLP_BEARER_TOKEN", "secret token")
    monkeypatch.setenv(name, value)

    result = CliRunner().invoke(app, ["telemetry", "serve"])

    assert result.exit_code == 1
    assert "Invalid telemetry configuration." in result.output
    assert "secret token" not in result.output
    uvicorn_run.assert_not_called()


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_telemetry_serve_rejects_invalid_cli_ports(
    uvicorn_run: Mock, port: str
) -> None:
    result = CliRunner().invoke(app, ["telemetry", "serve", "--port", port])

    assert result.exit_code == 2
    uvicorn_run.assert_not_called()


def test_telemetry_cli_serves_authenticated_production_receiver_in_subprocess(
    unused_tcp_port: int, tmp_path: Path
) -> None:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("UMBOD_")
    }
    environment.update(
        {
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
            "UMBOD_PROFILE": "production",
            "UMBOD_OTLP_ENABLED": "true",
            "UMBOD_OTLP_BEARER_TOKEN": "subprocess-collector-token",
            "UMBOD_OTLP_HOST": "127.0.0.1",
            "UMBOD_OTLP_PORT": str(unused_tcp_port),
        }
    )
    with (tmp_path / "telemetry-process.log").open("w+") as process_output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from umbod.cli.main import run; run()",
                "telemetry",
                "serve",
            ],
            cwd=tmp_path,
            env=environment,
            stdout=process_output,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{unused_tcp_port}",
                timeout=1.0,
                trust_env=False,
            ) as client:
                deadline = time.monotonic() + 20
                while True:
                    assert process.poll() is None, "Telemetry process exited before readiness"
                    try:
                        health = client.get("/health")
                        if health.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert time.monotonic() < deadline, "Telemetry receiver did not become healthy"
                    time.sleep(0.05)

                assert health.json() == {"status": "ok"}
                assert client.post("/v1/logs", json={}).status_code == 401
                response = client.post(
                    "/v1/logs",
                    json={},
                    headers={"Authorization": "Bearer subprocess-collector-token"},
                )
                assert response.status_code == 200
                assert client.get("/api/admin/connectors").status_code == 404
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
