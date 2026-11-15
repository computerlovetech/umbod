import asyncio
from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from tests.support.application_failures import CapturingApplicationFailures
from umbod.cli.cleanup import create_cleanup_jobs, run_cleanup
from umbod.cli.main import app
from umbod.config import AppConfig, InMemoryConnectorStoreConfig, SQLiteConnectorStoreConfig
from umbod.core.agent_behaviour.retention import DiagnosticRetention
from umbod.core.cleanup import CleanupJob
from umbod.core.diagnostics import ApplicationFailureKind
from umbod.core.persistence import Database, PersistenceReadiness, PersistenceRuntime
from umbod.core.usage.retention import UsageRetention
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider


class TrackingRuntime:
    def __init__(self) -> None:
        self.runtime = ConfiguredPersistenceRuntimeProvider(InMemoryConnectorStoreConfig()).create()
        self.calls: list[str] = []
        self.fail_readiness = False
        self.fail_shutdown = False

    @property
    def database(self) -> Database:
        return self.runtime.database

    @property
    def readiness(self) -> PersistenceReadiness:
        return self

    async def ensure_ready(self) -> None:
        self.calls.append("ready")
        if self.fail_readiness:
            raise RuntimeError("SECRET readiness credential")
        await self.runtime.readiness.ensure_ready()

    async def shutdown(self) -> None:
        self.calls.append("shutdown")
        await self.runtime.shutdown()
        if self.fail_shutdown:
            raise RuntimeError("SECRET shutdown credential")


class Provider:
    def __init__(self, runtime: TrackingRuntime) -> None:
        self.runtime = runtime
        self.calls = 0

    def create(self) -> PersistenceRuntime:
        self.calls += 1
        return self.runtime


class RecordingJob:
    failure_kind = ApplicationFailureKind.USAGE_RETENTION

    def __init__(self, calls: list[str], name: str, fail: bool) -> None:
        self.calls = calls
        self.name = name
        self.fail = fail

    async def run(self) -> None:
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError("SECRET job credential")


@dataclass
class CommandHarness:
    runtime: TrackingRuntime
    provider: Provider
    config: AppConfig
    failures: CapturingApplicationFailures


@pytest.fixture
def command(monkeypatch: pytest.MonkeyPatch) -> CommandHarness:
    runtime = TrackingRuntime()
    provider = Provider(runtime)
    config = AppConfig(connector_store=SQLiteConnectorStoreConfig(sqlite_path="unused.sqlite"))
    failures = CapturingApplicationFailures()
    monkeypatch.setattr("umbod.cli.cleanup.load_app_config", lambda env_file: config)
    monkeypatch.setattr("umbod.cli.cleanup.ConfiguredPersistenceRuntimeProvider", lambda settings: provider)
    monkeypatch.setattr("umbod.cli.cleanup.configure_logging", lambda name, level: None)
    monkeypatch.setattr("umbod.cli.cleanup.flush_logging", lambda: None)
    monkeypatch.setattr("umbod.cli.cleanup.create_application_failure_signal", lambda: failures)
    return CommandHarness(runtime, provider, config, failures)


def test_cli_registers_and_runs_all_jobs_even_when_collection_disabled(command: CommandHarness) -> None:
    command.config.personal_usage.enabled = False
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 0, result.output
    assert command.provider.calls == 1
    assert command.runtime.calls == ["ready", "shutdown"]
    jobs = create_cleanup_jobs(command.config, command.runtime)
    assert isinstance(jobs, tuple)
    assert tuple(type(job) for job in jobs) == (UsageRetention, DiagnosticRetention)


@pytest.mark.parametrize("store", [InMemoryConnectorStoreConfig(), SQLiteConnectorStoreConfig(sqlite_path=":memory:")])
def test_cli_rejects_process_local_storage(command: CommandHarness, store: InMemoryConnectorStoreConfig | SQLiteConnectorStoreConfig) -> None:
    command.config.connector_store = store
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 2
    assert "cannot clean server memory" in result.output
    assert command.provider.calls == 0


def test_cli_aggregate_failure_is_nonzero_and_other_jobs_run(command: CommandHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    def jobs(config: AppConfig, runtime: PersistenceRuntime) -> tuple[CleanupJob, ...]:
        return (
            RecordingJob(command.runtime.calls, "failed job", True),
            RecordingJob(command.runtime.calls, "following job", False),
        )

    monkeypatch.setattr("umbod.cli.cleanup.create_cleanup_jobs", jobs)
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 1
    assert command.runtime.calls == ["ready", "failed job", "following job", "shutdown"]
    assert len(command.failures.events) == 1
    assert "SECRET" not in result.output + command.failures.events[0].model_dump_json()


@pytest.mark.parametrize("phase", ["readiness", "shutdown"])
def test_cli_lifecycle_failure_is_sanitized_and_always_shuts_down(command: CommandHarness, phase: str) -> None:
    command.runtime.fail_readiness = phase == "readiness"
    command.runtime.fail_shutdown = phase == "shutdown"
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 1
    assert command.runtime.calls == ["ready", "shutdown"]
    assert command.provider.calls == 1
    assert len(command.failures.events) == 1
    assert "SECRET" not in result.output + command.failures.events[0].model_dump_json()


def test_cli_configuration_failure_does_not_print_private_values(command: CommandHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid_config(env_file: str) -> AppConfig:
        raise ValueError("SECRET configuration credential")

    monkeypatch.setattr("umbod.cli.cleanup.load_app_config", invalid_config)
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 1
    assert command.provider.calls == 0
    assert "SECRET" not in result.output + command.failures.events[0].model_dump_json()


def test_readiness_failure_evidence_survives_shutdown_failure(command: CommandHarness) -> None:
    command.runtime.fail_readiness = True
    command.runtime.fail_shutdown = True
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 1
    assert command.runtime.calls == ["ready", "shutdown"]
    assert len(command.failures.events) == 2
    assert "SECRET" not in result.output + repr(command.failures.events)


@pytest.mark.asyncio
async def test_readiness_cancellation_shuts_down_runtime() -> None:
    started = asyncio.Event()

    class BlockingReadinessRuntime(TrackingRuntime):
        async def ensure_ready(self) -> None:
            self.calls.append("ready")
            started.set()
            await asyncio.Event().wait()

    runtime = BlockingReadinessRuntime()
    failures = CapturingApplicationFailures()
    task = asyncio.create_task(run_cleanup(AppConfig(), runtime, failures))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime.calls == ["ready", "shutdown"]
    assert failures.events == []


@pytest.mark.asyncio
async def test_cancellation_propagates_and_runtime_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = TrackingRuntime()
    started = asyncio.Event()

    class BlockingJob:
        failure_kind = ApplicationFailureKind.USAGE_RETENTION

        async def run(self) -> None:
            started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr("umbod.cli.cleanup.create_cleanup_jobs", lambda config, runtime: (BlockingJob(),))
    failures = CapturingApplicationFailures()
    task = asyncio.create_task(run_cleanup(AppConfig(), runtime, failures))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime.calls == ["ready", "shutdown"]
    assert failures.events == []
