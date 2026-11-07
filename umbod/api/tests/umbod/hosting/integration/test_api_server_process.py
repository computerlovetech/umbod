import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest


def _ports(count: int) -> tuple[int, ...]:
    sockets = [socket.socket() for _ in range(count)]
    try:
        for listener in sockets:
            listener.bind(("127.0.0.1", 0))
        return tuple(listener.getsockname()[1] for listener in sockets)
    finally:
        for listener in sockets:
            listener.close()



def _wait_for(
    condition: Callable[[], bool], process: subprocess.Popen[bytes], log: Path,
    *, timeout: float, description: str,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert process.poll() is None, log.read_text()
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {description}: {log.read_text()}")



def _healthy(origins: tuple[str, str]) -> bool:
    try:
        return (
            httpx.get(f"{origins[0]}/system/health", timeout=0.5).status_code == 200
            and httpx.get(f"{origins[1]}/ready", timeout=0.5).status_code == 200
        )
    except httpx.TransportError:
        return False



def _metrics_recorded(origin: str, samples: frozenset[str]) -> bool:
    try:
        response = httpx.get(f"{origin}/metrics", timeout=0.5)
        return response.status_code == 200 and samples.issubset(response.text.splitlines())
    except httpx.TransportError:
        return False



def _count(origin: str) -> int:
    response = httpx.post(
        f"{origin}/api/admin/telemetry/log-counts",
        json={
            "time_range": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
            "filters": [],
            "group_by": [],
            "bucketing": {"kind": "none"},
            "max_groups": 10,
        },
        timeout=3,
    )
    assert response.status_code == 200, response.text
    return response.json()["rows"][0]["count"]



@pytest.mark.parametrize("reload", [False, True])
def test_api_command_serves_private_collector_and_shared_analytics(
    tmp_path: Path,
    reload: bool,
) -> None:
    api_port, collector_port, rest_metrics, mcp_port, mcp_metrics = _ports(5)
    origins = (f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{collector_port}")
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    marker = tmp_path / "reload_marker.py"
    marker.write_text("generation = 1\n")
    pids = tmp_path / "listener-pids.txt"
    pids.write_text("")
    (tmp_path / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\nfrom socket import socket\nfrom uvicorn import Server\n"
        "original_startup = Server.startup\n"
        "async def startup(self: Server, sockets: list[socket]) -> None:\n"
        "    await original_startup(self, sockets=sockets)\n"
        "    if self.started:\n"
        "        with Path(os.environ['LISTENER_TEST_PID_PATH']).open('a') as output:\n"
        "            output.write(str(os.getpid()) + ',' + str(self.config.port) + '\\n')\n"
        "Server.startup = startup\n"
    )
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("UMBOD_")
    }
    environment.update(
        {
            "UMBOD_PROFILE": "local",
            "UMBOD_AUTH": "none",
            "UMBOD_ROOT_SECRET": "listener-test-root",
            "UMBOD_REST_PORT": str(api_port),
            "UMBOD_REST_METRICS_PORT": str(rest_metrics),
            "UMBOD_MCP_PORT": str(mcp_port),
            "UMBOD_MCP_METRICS_PORT": str(mcp_metrics),
            "UMBOD_OTLP_ENABLED": "true",
            "UMBOD_OTLP_BEARER_TOKEN": "listener-test-token",
            "UMBOD_OTLP_HOST": "127.0.0.1",
            "UMBOD_OTLP_PORT": str(collector_port),
            "UMBOD_TELEMETRY_ANALYTICS_ENABLED": "true",
            "UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH": str(
                tmp_path / "analytics.sqlite3"
            ),
            "UMBOD_CONNECTOR_STORE": "inmemory",
            "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH": str(declaration),
            "UMBOD_DATA_DIR": str(tmp_path / "data"),
            "WATCHFILES_FORCE_POLLING": "true",
            "LISTENER_TEST_PID_PATH": str(pids),
            "PYTHONPATH": str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }
    )
    log = tmp_path / "host.log"
    arguments = [
        sys.executable,
        "-c",
        "from umbod.cli.main import run; run()",
        "api",
        "serve",
        "--host",
        "127.0.0.1",
    ]
    if reload:
        arguments.append("--reload")
    with log.open("wb") as output:
        process = subprocess.Popen(
            arguments,
            cwd=tmp_path,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for(
                lambda: _healthy(origins), process, log,
                timeout=60, description="API and collector startup",
            )
            for signal in ("logs", "metrics", "traces"):
                response = httpx.post(f"{origins[0]}/v1/{signal}", json={}, timeout=3)
                assert response.status_code == 404
            assert (
                httpx.post(
                    f"{origins[1]}/api/admin/telemetry/log-counts", json={}, timeout=3
                ).status_code
                == 404
            )
            assert (
                httpx.post(f"{origins[1]}/v1/logs", json={}, timeout=3).status_code
                == 401
            )
            exported = httpx.post(
                f"{origins[1]}/v1/logs",
                json={
                    "resourceLogs": [
                        {
                            "scopeLogs": [
                                {
                                    "logRecords": [
                                        {
                                            "timeUnixNano": "1767226200000000000",
                                            "eventName": "tool.completed",
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                headers={"Authorization": "Bearer listener-test-token"},
                timeout=3,
            )
            assert exported.status_code == 200, exported.text
            assert _count(origins[0]) == 1
            metrics_origin = f"http://127.0.0.1:{rest_metrics}"
            expected_samples = frozenset({
                'umbod_rest_requests_total{method="POST",route="/admin/telemetry/log-counts",status_class="2xx"} 1.0',
                'umbod_collector_requests_total{method="POST",route="/v1/logs",status_class="2xx"} 1.0',
                'umbod_collector_requests_total{method="POST",route="/v1/logs",status_class="4xx"} 1.0',
                'umbod_collector_request_duration_seconds_count{method="POST",route="/v1/logs",status_class="2xx"} 1.0',
                "umbod_collector_log_records_accepted_total 1.0",
            })
            _wait_for(
                lambda: _metrics_recorded(metrics_origin, expected_samples), process, log,
                timeout=5, description="request metrics publication",
            )
            metrics = httpx.get(f"{metrics_origin}/metrics", timeout=3)
            assert metrics.status_code == 200
            assert expected_samples.issubset(metrics.text.splitlines()), metrics.text
            assert 'route="/ready"' not in metrics.text
            assert "listener-test-token" not in metrics.text
            serving_pids = {row.split(",")[0] for row in pids.read_text().splitlines()}
            assert len(serving_pids) == 1
            assert {
                int(row.split(",")[1]) for row in pids.read_text().splitlines()
            } == {api_port, collector_port, rest_metrics}
            if reload:
                marker.write_text("generation = 2\n")
                _wait_for(
                    lambda: (
                        len(
                            {row.split(",")[0] for row in pids.read_text().splitlines()}
                        )
                        >= 2
                        and _healthy(origins)
                    ),
                    process,
                    log,
                    timeout=60,
                    description="reloaded API and collector readiness",
                )
                assert _count(origins[0]) == 1
            else:
                assert serving_pids == {str(process.pid)}
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise
        assert process.returncode == 0, log.read_text()
    for port in (api_port, collector_port, rest_metrics):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))

