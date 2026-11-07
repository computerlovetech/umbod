import asyncio
import sys
import threading
from pathlib import Path

import pytest

from umbod.config import AppConfig, OtlpReceiverConfig
from umbod.hosting.api_server import (
    ProcessShutdownDeadline,
    serve_api,
    validate_listener_ports,
)
from umbod.core.telemetry.analytics import (
    TelemetryAnalyticsReader,
    TelemetryAnalyticsRuntime,
    TelemetryAnalyticsWriter,
)


@pytest.mark.asyncio
async def test_startup_failure_signals_shutdown_before_entering_runtime_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopping = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_allowed = asyncio.Event()

    class FailingStartupRuntime:
        async def ensure_ready(self) -> None:
            raise RuntimeError("startup failed")

        async def shutdown(self) -> None:
            assert stopping.is_set()
            cleanup_started.set()
            await cleanup_allowed.wait()

        def create_reader(self) -> TelemetryAnalyticsReader:
            raise AssertionError("Startup failure must not create an analytics reader")

        def create_writer(self) -> TelemetryAnalyticsWriter:
            raise AssertionError("Startup failure must not create an analytics writer")

    runtime = FailingStartupRuntime()

    def create_runtime(settings: AppConfig) -> TelemetryAnalyticsRuntime:
        return runtime

    monkeypatch.setattr(
        "umbod.hosting.api_server.create_configured_analytics_runtime", create_runtime
    )
    task = asyncio.create_task(serve_api(AppConfig(), "127.0.0.1", 8000, stopping))
    try:
        await asyncio.wait_for(cleanup_started.wait(), timeout=1)
        assert stopping.is_set()
    finally:
        cleanup_allowed.set()
        with pytest.raises(RuntimeError, match="startup failed"):
            await task


def test_shutdown_deadline_requests_nonzero_exit_when_cleanup_stalls() -> None:
    terminated = threading.Event()
    codes: list[int] = []

    def terminate(code: int) -> None:
        codes.append(code)
        terminated.set()

    deadline = ProcessShutdownDeadline(0.01, terminate)
    deadline.arm()
    deadline.arm()
    try:
        assert terminated.wait(timeout=1)
        assert codes == [1]
    finally:
        deadline.cancel()


def test_completed_shutdown_cancels_process_deadline() -> None:
    terminated = threading.Event()

    def terminate(code: int) -> None:
        terminated.set()

    deadline = ProcessShutdownDeadline(0.02, terminate)
    deadline.arm()
    deadline.cancel()
    assert not terminated.wait(timeout=0.04)


@pytest.mark.asyncio
async def test_shutdown_deadline_exits_even_when_main_thread_is_blocked(
    tmp_path: Path,
) -> None:
    startup_timeout = 30
    shutdown_timeout = 5
    diagnostics = tmp_path / "shutdown-deadline.stderr"
    with diagnostics.open("wb") as output:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            (
                "import os, sys, threading; "
                "from umbod.hosting.api_server import ProcessShutdownDeadline; "
                "deadline = ProcessShutdownDeadline(0.02, os._exit); "
                "print('ready', flush=True); "
                "assert sys.stdin.readline() == 'shutdown\\n'; "
                "deadline.arm(); threading.Event().wait()"
            ),
            cwd=tmp_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=output,
        )
        phase = "startup"
        try:
            try:
                assert process.stdout is not None
                assert process.stdin is not None
                ready = await asyncio.wait_for(process.stdout.readline(), startup_timeout)
                assert ready == b"ready\n", diagnostics.read_text()
                phase = "shutdown"
                process.stdin.write(b"shutdown\n")
                await process.stdin.drain()
                await asyncio.wait_for(process.communicate(), shutdown_timeout)
                assert process.returncode == 1, diagnostics.read_text()
            finally:
                if process.returncode is None:
                    process.kill()
                await process.communicate()
        except TimeoutError as error:
            raise AssertionError(
                f"Timed out during deadline subprocess {phase}: {diagnostics.read_text()}"
            ) from error


@pytest.mark.parametrize("port", [0, 65536, 8011, 8012])
def test_effective_rest_port_rejects_invalid_or_reserved_values(port: int) -> None:
    with pytest.raises(ValueError):
        validate_listener_ports(AppConfig(), port)


def test_explicit_api_port_cannot_collide_with_enabled_collector() -> None:
    settings = AppConfig(otlp_receiver=OtlpReceiverConfig(enabled=True, port=4318))
    with pytest.raises(ValueError, match="Collector listener port"):
        validate_listener_ports(settings, 4318)
