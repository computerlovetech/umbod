import asyncio
from datetime import UTC, datetime

import typer

from umbod.config import AppConfig, InMemoryConnectorStoreConfig, load_app_config
from umbod.core.agent_behaviour.retention import create_diagnostic_retention
from umbod.core.cleanup import CleanupJob, CleanupRunner
from umbod.core.diagnostics import (
    ApplicationFailure, ApplicationFailureKind, NoFailureContext, report_application_failure,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.core.signals import SignalPublisher
from umbod.core.usage.retention import UsageRetention
from umbod.core.usage.store import DatabaseUsageStore
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.logging import configure_logging, create_application_failure_signal, flush_logging


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_cleanup_jobs(config: AppConfig, runtime: PersistenceRuntime) -> tuple[CleanupJob, ...]:
    return (
        UsageRetention(DatabaseUsageStore(runtime.database), config.personal_usage.retention_days, utc_now),
        create_diagnostic_retention(runtime.database),
    )


async def run_cleanup(
    config: AppConfig, runtime: PersistenceRuntime,
    application_failures: SignalPublisher[ApplicationFailure],
) -> bool:
    succeeded = False
    try:
        try:
            await runtime.readiness.ensure_ready()
            succeeded = await CleanupRunner(
                create_cleanup_jobs(config, runtime), config.cleanup.job_timeout_seconds, application_failures,
            ).run()
        except Exception as error:
            report_application_failure(application_failures, ApplicationFailureKind.CLEANUP_INVOCATION, error, NoFailureContext())
    finally:
        try:
            await runtime.shutdown()
        except Exception as error:
            report_application_failure(application_failures, ApplicationFailureKind.CLEANUP_INVOCATION, error, NoFailureContext())
            succeeded = False
    return succeeded


def cleanup() -> None:
    configure_logging("umbod-cleanup", "INFO")
    failures = create_application_failure_signal()
    try:
        config = load_app_config(".env")
        configure_logging(config.runtime.app_name, config.runtime.log_level)
        store = config.connector_store
        if isinstance(store, InMemoryConnectorStoreConfig) or store.sqlite_path == ":memory:":
            typer.echo("Cleanup requires persistent storage; it cannot clean server memory.", err=True)
            raise typer.Exit(code=2)
        runtime = ConfiguredPersistenceRuntimeProvider(store).create()
        succeeded = asyncio.run(run_cleanup(config, runtime, failures))
    except typer.Exit:
        raise
    except Exception as error:
        report_application_failure(failures, ApplicationFailureKind.CLEANUP_INVOCATION, error, NoFailureContext())
        typer.echo("Cleanup failed. Check configuration and sanitized diagnostics.", err=True)
        raise typer.Exit(code=1) from None
    finally:
        flush_logging()
    if not succeeded:
        typer.echo("Cleanup finished with failed jobs. Check sanitized diagnostics.", err=True)
        raise typer.Exit(code=1)
    typer.echo("Cleanup complete.")
