import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from umbod.cli.main import app
from umbod.config import SQLiteConnectorStoreConfig
from umbod.core.agent_behaviour import AgentBehaviourService, PatternAssessment, SubmitDiagnosticReport
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.agent_behaviour.schema import DEDUPE_TABLE, REPORT_LIST_TABLE, REPORT_TABLE
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import AllFields, NoFilter, PersistenceRuntime, Query, Unordered
from umbod.core.usage.models import UnavailableUsageTool
from umbod.core.usage.models import OwnedUsageQuery, UsageBatch, UsageKind, UsageOutcome, UsageRecord
from umbod.core.usage.store import DatabaseUsageStore
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider


OWNER = "a" * 64


def runtime(path: Path) -> PersistenceRuntime:
    return ConfiguredPersistenceRuntimeProvider(SQLiteConnectorStoreConfig(sqlite_path=str(path))).create()


def record(at: datetime) -> UsageRecord:
    nanos = int(at.timestamp()) * 1_000_000_000
    return UsageRecord(
        tool=UnavailableUsageTool(kind='unavailable'),
        event_id=uuid4(), owner_id=OWNER, occurred_at_unix_nano=nanos,
        observed_at_unix_nano=nanos, kind=UsageKind.TOOL, outcome=UsageOutcome.SUCCESS,
        duration_ms=1, service_name="test", trace_id="", span_id="",
    )


async def seed(path: Path, now: datetime) -> None:
    persistence = runtime(path)
    try:
        await persistence.readiness.ensure_ready()
        usage = DatabaseUsageStore(persistence.database)
        await usage.append_usage(UsageBatch(records=(record(now - timedelta(days=2)), record(now))))
        old_time = now - timedelta(days=61)
        behaviour = AgentBehaviourService(DatabaseAgentBehaviourStore(persistence.database), lambda: old_time, uuid4)
        configuration = await behaviour.get_configuration()
        playbook = configuration.playbooks[0]
        caller = CallerContext(
            authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
            subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.invalid"), subject="owner"),
        )
        await behaviour.submit_report(caller, SubmitDiagnosticReport(
            idempotency_key=uuid4(), configuration_revision=configuration.revision,
            playbook_id=playbook.id, trigger="user_requested",
            assessments=tuple(PatternAssessment(pattern_id=pattern_id, status="not_assessed", summary="Required context was unavailable", evidence=()) for pattern_id in playbook.pattern_ids),
        ))
    finally:
        await persistence.shutdown()


async def assert_persisted_cleanup(path: Path, now: datetime) -> None:
    persistence = runtime(path)
    try:
        await persistence.readiness.ensure_ready()
        summary = await DatabaseUsageStore(persistence.database).count_usage(OwnedUsageQuery(owner_id=OWNER, days=7, as_of=now))
        assert summary.totals.total == 1
        async with persistence.database.read_session() as session:
            assert not await session.find_many(REPORT_TABLE, Query(NoFilter(), AllFields(), Unordered()))
            assert not await session.find_many(REPORT_LIST_TABLE, Query(NoFilter(), AllFields(), Unordered()))
            assert not await session.find_many(DEDUPE_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    finally:
        await persistence.shutdown()


def test_cli_reopens_configured_sqlite_and_durably_cleans_all_jobs_with_collection_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", root.level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "handlers", list(logger.handlers))
        monkeypatch.setattr(logger, "propagate", logger.propagate)
    path = tmp_path / "cleanup.sqlite"
    now = datetime.now(UTC)
    asyncio.run(seed(path, now))
    monkeypatch.setattr("umbod.cli.cleanup.utc_now", lambda: now)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "sqlite")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE_SQLITE_PATH", str(path))
    monkeypatch.setenv("UMBOD_PERSONAL_USAGE_ENABLED", "false")
    monkeypatch.setenv("UMBOD_PERSONAL_USAGE_RETENTION_DAYS", "1")
    result = CliRunner().invoke(app, ["cleanup"])
    assert result.exit_code == 0, result.output
    assert "Cleanup complete" in result.output
    asyncio.run(assert_persisted_cleanup(path, now))
