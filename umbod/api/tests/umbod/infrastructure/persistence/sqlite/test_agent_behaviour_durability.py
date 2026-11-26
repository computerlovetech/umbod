import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.agent_behaviour import AgentBehaviourService, PublishConfiguration, ReportGone, ReportQuery, ReportingDisabled, StorageUnavailable, SubmitDiagnosticReport
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import DatabaseSession, TransactionMode


def _clock() -> datetime:
    return datetime(2026, 6, 1, 12, tzinfo=UTC)


def _inputs() -> tuple[CallerContext, PublishConfiguration, SubmitDiagnosticReport]:
    caller = CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.invalid"), subject="user-a"))
    publication = PublishConfiguration.model_validate({
        "expected_revision": 1,
        "reporting_enabled": True,
        "patterns": [{"id": "task", "name": "Task", "description": "Task failed", "assessment_prompt": "Assess task completion", "inclusion_criteria": "", "exclusion_criteria": "", "categories": [], "polarity": "negative", "enabled": True}],
        "playbooks": [{"id": "review", "name": "Review", "collection_instructions": "Review available context", "pattern_ids": ["task"], "enabled": True}],
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
            playbooks = (playbooks[0].model_copy(update={"collection_instructions": "Keep dormant reporting instructions", "enabled": False}),)
        else:
            patterns = ()
            playbooks = ()
        saved = await service.publish_configuration(PublishConfiguration(reporting_enabled=False, expected_revision=1, patterns=patterns, playbooks=playbooks))
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
async def test_sqlite_submission_queued_behind_disable_uses_committed_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    caller, publication, submission = _inputs()
    database_path = tmp_path / "reporting-race.sqlite3"
    async with AsyncExitStack() as cleanup:
        runtime = await prepared_sqlite_runtime(database_path)
        cleanup.push_async_callback(runtime.shutdown)
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4)
        active = await service.publish_configuration(publication)
        disabled = active.model_copy(update={"revision": active.revision + 1, "reporting_enabled": False})
        write_requested = asyncio.Event()
        open_session = runtime.database.session

        @asynccontextmanager
        async def observe_session(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
            write_requested.set()
            async with open_session(mode=mode) as session:
                yield session

        monkeypatch.setattr(runtime.database, "session", observe_session)
        with closing(sqlite3.connect(database_path)) as writer:
            with writer:
                writer.execute("UPDATE agent_behaviour_configuration SET configuration = ?", (disabled.model_dump_json(),))
                async with asyncio.TaskGroup() as group:
                    async def submit() -> None:
                        with pytest.raises(ReportingDisabled):
                            await service.submit_report(caller, submission)

                    group.create_task(submit())
                    await asyncio.wait_for(write_requested.wait(), timeout=5)
                    writer.commit()
            counts = writer.execute(
                "SELECT (SELECT COUNT(*) FROM agent_behaviour_reports), "
                "(SELECT COUNT(*) FROM agent_behaviour_report_index), "
                "(SELECT COUNT(*) FROM agent_behaviour_receipts)"
            ).fetchone()
        assert counts == (0, 0, 0)


LEGACY_FACTORY_INSTRUCTIONS = (
    "Review only the current task context and tool results you are authorized to use. Assess every selected pattern. "
    "Record a short factual summary and up to three minimal observations for each observed pattern. "
    "Use not_assessed when context is insufficient. Never collect full transcripts, credentials, personal data, or hidden reasoning."
)
LEGACY_MODE_SUFFIX = " Report only when requested unless automatic reporting is explicitly allowed and the user and client permit it."


@pytest.mark.asyncio
@pytest.mark.parametrize("previously_enabled,legacy_proactive", [(True, False), (False, True)])
async def test_sqlite_reads_legacy_configuration_and_only_rewrites_exact_factory_text(
    tmp_path: Path, previously_enabled: bool, legacy_proactive: bool,
) -> None:
    database_path = tmp_path / "legacy-configuration.sqlite3"
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4)
        current = await service.get_configuration()
        custom_text = "Administrator-edited collection instructions." + LEGACY_MODE_SUFFIX
        payload = current.model_dump(mode="json")
        del payload["reporting_enabled"]
        payload["revision"] = 6
        legacy_default = {
            **payload["playbooks"][0], "collection_instructions": LEGACY_FACTORY_INSTRUCTIONS + LEGACY_MODE_SUFFIX,
            "enabled": False, "allow_proactive": legacy_proactive,
        }
        payload["playbooks"] = [legacy_default, {
            **legacy_default, "id": "custom-review", "enabled": previously_enabled,
            "collection_instructions": custom_text,
        }]
        with sqlite3.connect(database_path) as connection:
            connection.execute("UPDATE agent_behaviour_configuration SET configuration = ?", (json.dumps(payload),))
    finally:
        await runtime.shutdown()

    restarted = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(restarted.database), _clock, uuid4)
        restored = await service.get_configuration()
        assert restored.revision == 6
        assert restored.reporting_enabled is previously_enabled
        assert restored.patterns == current.patterns
        assert restored.playbooks[0].collection_instructions == LEGACY_FACTORY_INSTRUCTIONS
        assert restored.playbooks[1].collection_instructions == custom_text
        assert [playbook.enabled for playbook in restored.playbooks] == [False, previously_enabled]
        assert all("allow_proactive" not in playbook.model_dump() for playbook in restored.playbooks)
        if previously_enabled:
            await service.get_instructions("custom-review")
        else:
            with pytest.raises(ReportingDisabled):
                await service.get_instructions("custom-review")
        await service.publish_configuration(PublishConfiguration(
            expected_revision=restored.revision, reporting_enabled=False, patterns=restored.patterns, playbooks=restored.playbooks,
        ))
        with sqlite3.connect(database_path) as connection:
            stored = json.loads(connection.execute("SELECT configuration FROM agent_behaviour_configuration").fetchone()[0])
        assert stored["reporting_enabled"] is False
        assert all("allow_proactive" not in playbook for playbook in stored["playbooks"])
    finally:
        await restarted.shutdown()


@pytest.mark.asyncio
async def test_sqlite_legacy_report_keeps_historical_instructions_and_duplicate_receipt(tmp_path: Path) -> None:
    caller, _, submission = _inputs()
    database_path = tmp_path / "legacy-report.sqlite3"
    runtime = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(runtime.database), _clock, uuid4)
        defaults = await service.get_configuration()
        legacy_text = LEGACY_FACTORY_INSTRUCTIONS + LEGACY_MODE_SUFFIX
        historical_playbook = defaults.playbooks[0].model_copy(update={"collection_instructions": legacy_text})
        await service.publish_configuration(PublishConfiguration(
            expected_revision=defaults.revision, reporting_enabled=True, patterns=defaults.patterns, playbooks=(historical_playbook,),
        ))
        submission = SubmitDiagnosticReport.model_validate({
            **submission.model_dump(mode="json"), "playbook_id": historical_playbook.id, "trigger": "proactive",
            "assessments": [
                {"pattern_id": pattern.id, "status": "not_observed", "summary": "", "evidence": []}
                for pattern in defaults.patterns
            ],
        })
        receipt = await service.submit_report(caller, submission)
        original = await service.get_report(receipt.report_id)
        payload = original.model_dump(mode="json")
        payload["instructions"]["reporting_guidance"] = "Historical guidance: allow_proactive=true."
        payload["instructions"]["playbook"]["allow_proactive"] = True
        with sqlite3.connect(database_path) as connection:
            connection.execute("UPDATE agent_behaviour_reports SET report = ? WHERE report_id = ?", (json.dumps(payload), str(receipt.report_id)))
    finally:
        await runtime.shutdown()

    restarted = await prepared_sqlite_runtime(database_path)
    try:
        service = AgentBehaviourService(DatabaseAgentBehaviourStore(restarted.database), _clock, uuid4)
        assert (await service.get_instructions(historical_playbook.id)).playbook.collection_instructions == legacy_text
        restored = await service.get_report(receipt.report_id)
        del payload["instructions"]["playbook"]["allow_proactive"]
        assert restored.model_dump(mode="json") == payload
        duplicate = await service.submit_report(caller, submission)
        assert duplicate == receipt.model_copy(update={"duplicate": True})
        assert (await service.list_reports(ReportQuery())).items[0].trigger == "proactive"
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
