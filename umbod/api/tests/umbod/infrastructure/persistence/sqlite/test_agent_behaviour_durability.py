import asyncio
import sqlite3
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.agent_behaviour import AgentBehaviourService, PublishConfiguration, ReportGone, ReportQuery, StorageUnavailable, SubmitDiagnosticReport
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity


def _clock() -> datetime:
    return datetime(2026, 6, 1, 12, tzinfo=UTC)


def _inputs() -> tuple[CallerContext, PublishConfiguration, SubmitDiagnosticReport]:
    caller = CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.invalid"), subject="user-a"))
    publication = PublishConfiguration.model_validate({
        "expected_revision": 1,
        "patterns": [{"id": "task", "name": "Task", "description": "Task failed", "assessment_prompt": "Assess task completion", "inclusion_criteria": "", "exclusion_criteria": "", "categories": [], "polarity": "negative", "enabled": True}],
        "playbooks": [{"id": "review", "name": "Review", "collection_instructions": "Review available context", "pattern_ids": ["task"], "enabled": True, "allow_proactive": False}],
    })
    submission = SubmitDiagnosticReport.model_validate({"idempotency_key": str(uuid4()), "configuration_revision": 2, "playbook_id": "review", "trigger": "user_requested", "assessments": [{"pattern_id": "task", "status": "observed", "summary": "Task was blocked", "evidence": []}]})
    return caller, publication, submission


@pytest.mark.asyncio
async def test_sqlite_restart_preserves_configuration_report_receipt_and_deletion(tmp_path: Path) -> None:
    caller, publication, submission = _inputs()
    database_path = tmp_path / "behaviour.sqlite3"
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4)
        configuration = await service.publish_configuration(publication)
        receipt = await service.submit_report(caller, submission)
    finally:
        await runtime.shutdown()
    restarted = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(restarted.database), _clock, uuid4)
        assert await service.get_configuration() == configuration
        assert (await service.get_report(receipt.report_id)).submission == submission
        duplicate = await service.submit_report(caller, submission)
        assert duplicate.report_id == receipt.report_id
        assert duplicate.duplicate is True
        await service.delete_report(receipt.report_id)
    finally:
        await restarted.shutdown()
    final = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(final.database), _clock, uuid4)
        assert (await service.list_reports(ReportQuery())).total == 0
        with pytest.raises(ReportGone):
            await service.submit_report(caller, submission)
    finally:
        await final.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["remove", "edit", "disable", "empty", "dormant"])
async def test_sqlite_restart_never_reseeds_customized_defaults(tmp_path: Path, change: str) -> None:
    database_path = tmp_path / "defaults.sqlite3"
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4)
        defaults = await service.get_configuration()
        assert defaults.revision == 1
        patterns = defaults.patterns
        playbooks = defaults.playbooks
        if change == "remove":
            patterns = patterns[1:]
            playbooks = (playbooks[0].model_copy(update={"pattern_ids": tuple(pattern.id for pattern in patterns)}),)
        elif change == "edit":
            patterns = (patterns[0].model_copy(update={"assessment_prompt": "Administrator criteria"}), *patterns[1:])
            playbooks = (playbooks[0].model_copy(update={"collection_instructions": "Administrator instructions"}),)
        elif change == "disable":
            patterns = tuple(pattern.model_copy(update={"enabled": False}) for pattern in patterns)
            playbooks = (playbooks[0].model_copy(update={"enabled": False}),)
        elif change == "dormant":
            patterns = ()
            playbooks = (playbooks[0].model_copy(update={"collection_instructions": "Keep dormant reporting instructions", "enabled": False, "allow_proactive": True}),)
        else:
            patterns = ()
            playbooks = ()
        saved = await service.publish_configuration(PublishConfiguration(expected_revision=1, patterns=patterns, playbooks=playbooks))
    finally:
        await runtime.shutdown()
    restarted = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(restarted.database), _clock, uuid4)
        assert await service.get_configuration() == saved
        assert await service.get_configuration() == saved
        assert service.get_defaults() == defaults
    finally:
        await restarted.shutdown()


@pytest.mark.asyncio
async def test_sqlite_independent_connections_first_reads_cannot_overwrite_first_publication(tmp_path: Path) -> None:
    _, publication, _ = _inputs()
    database_path = tmp_path / "concurrent-defaults.sqlite3"
    async with AsyncExitStack() as cleanup:
        services: list[AgentBehaviourService] = []
        for _ in range(4):
            runtime = await prepared_sqlite_runtime(database_path)
            cleanup.push_async_callback(runtime.shutdown)
            services.append(AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4))
        results = await asyncio.gather(*(service.get_configuration() for service in services), services[0].publish_configuration(publication))
        saved = results[-1]
        assert saved.revision == 2
        assert saved.patterns == publication.patterns
        assert all(configuration.revision in {1, 2} for configuration in results)
        assert all(configuration == saved for configuration in await asyncio.gather(*(service.get_configuration() for service in services)))
    restarted = await prepared_sqlite_runtime(database_path)
    try:
        assert await DatabaseAgentBehaviourStore(restarted.database).get_configuration() == saved
    finally:
        await restarted.shutdown()


@pytest.mark.asyncio
async def test_report_listing_does_not_read_or_decode_detail_snapshots(tmp_path: Path) -> None:
    caller, publication, submission = _inputs()
    database_path = tmp_path / "projection.sqlite3"
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4)
        await service.publish_configuration(publication)
        receipt = await service.submit_report(caller, submission)
        with sqlite3.connect(database_path) as connection:
            connection.execute("UPDATE agent_behaviour_reports SET report = ? WHERE report_id = ?", ("{}", str(receipt.report_id)))
        page = await service.list_reports(ReportQuery(limit=1))
        assert page.total == 1
        assert page.items[0].report_id == receipt.report_id
        with pytest.raises(StorageUnavailable):
            await service.get_report(receipt.report_id)
    finally:
        await runtime.shutdown()
