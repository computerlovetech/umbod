import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest


def _listener_ports() -> tuple[int, ...]:
    sockets = [socket.socket() for _ in range(5)]
    try:
        for listener in sockets:
            listener.bind(("127.0.0.1", 0))
        return tuple(listener.getsockname()[1] for listener in sockets)
    finally:
        for listener in sockets:
            listener.close()


def _wait_for(
    condition: Callable[[], bool], process: subprocess.Popen[bytes], log: Path,
) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        assert process.poll() is None, log.read_text()
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(f"MCP listener condition was not met: {log.read_text()}")


def _healthy(client: httpx.Client, origins: tuple[str, ...]) -> bool:
    try:
        return all(
            client.get(f"{origin}/system/health", timeout=0.5).status_code == 200
            for origin in origins
        )
    except httpx.TransportError:
        return False


def _latest_listener_processes(path: Path) -> dict[int, int]:
    return {
        int(port): int(pid)
        for pid, port in (line.split(",") for line in path.read_text().splitlines())
    }


@pytest.mark.parametrize("reload", [False, True])
def test_mcp_command_defaults_to_separate_listeners_with_metrics_and_clean_shutdown(
    tmp_path: Path, reload: bool,
) -> None:
    public_port, admin_port, metrics_port, rest_port, rest_metrics_port = _listener_ports()
    origins = (f"http://127.0.0.1:{public_port}", f"http://127.0.0.1:{admin_port}")
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    marker = tmp_path / "reload_trigger.py"
    marker.write_text("revision = 1\n")
    pids = tmp_path / "listener-pids.txt"
    pids.write_text("")
    (tmp_path / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\nfrom socket import socket\nfrom uvicorn import Server\n"
        "original_startup = Server.startup\n"
        "async def startup(self: Server, sockets: list[socket] | None = None) -> None:\n"
        "    await original_startup(self, sockets=sockets)\n"
        "    if self.started:\n"
        "        with Path(os.environ['LISTENER_TEST_PID_PATH']).open('a') as output:\n"
        "            output.write(str(os.getpid()) + ',' + str(self.config.port) + '\\n')\n"
        "Server.startup = startup\n"
    )
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("UMBOD_")
    }
    environment.update({
        "UMBOD_PROFILE": "local",
        "UMBOD_AUTH": "none",
        "UMBOD_ROOT_SECRET": "mcp-listener-test-root",
        "UMBOD_REST_PORT": str(rest_port),
        "UMBOD_REST_METRICS_PORT": str(rest_metrics_port),
        "UMBOD_MCP_PORT": str(public_port),
        "UMBOD_MCP_METRICS_PORT": str(metrics_port),
        "UMBOD_MCP_MESSAGING_TRANSPORT": "sql",
        "UMBOD_MCP_ADMINISTRATOR_HOST": "127.0.0.1",
        "UMBOD_MCP_ADMINISTRATOR_PORT": str(admin_port),
        "UMBOD_MCP_ADMINISTRATOR_BASE_URL": origins[1],
        "UMBOD_TELEMETRY_ANALYTICS_ENABLED": "false",
        "UMBOD_CONNECTOR_STORE": "sqlite",
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH": str(declaration),
        "UMBOD_DATA_DIR": str(tmp_path / "data"),
        "LISTENER_TEST_PID_PATH": str(pids),
        "PYTHONPATH": str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    })
    arguments = [
        sys.executable, "-c", "from umbod.cli.main import run; run()",
        "mcp", "serve", "--host", "127.0.0.1",
    ]
    if reload:
        arguments.append("--reload")
    log = tmp_path / "mcp-host.log"
    with log.open("wb") as output, httpx.Client(trust_env=False) as client:
        process = subprocess.Popen(
            arguments, cwd=tmp_path, env=environment,
            stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            _wait_for(lambda: _healthy(client, origins), process, log)
            initial = _latest_listener_processes(pids)
            assert set(initial) == {public_port, admin_port, metrics_port}
            assert len(set(initial.values())) == 1
            if not reload:
                assert set(initial.values()) == {process.pid}
            metrics = client.get(f"http://127.0.0.1:{metrics_port}/metrics", timeout=3)
            assert metrics.status_code == 200
            if reload:
                marker.write_text("revision = 2\n")

                def restarted() -> bool:
                    current = _latest_listener_processes(pids)
                    return (
                        set(current) == set(initial)
                        and len(set(current.values())) == 1
                        and current[public_port] != initial[public_port]
                        and _healthy(client, origins)
                    )

                _wait_for(restarted, process, log)
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise
        assert process.returncode == 0, log.read_text()
    for port in (public_port, admin_port, metrics_port):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
