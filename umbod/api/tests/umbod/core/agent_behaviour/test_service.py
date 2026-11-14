import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.agent_behaviour import AgentBehaviourService, CallerNotAuthorized, ConfigurationInvalid, IdempotencyConflict, InstructionsUnavailable, ProactiveDisabled, PublishConfiguration, ReportGone, ReportInvalid, ReportNotFound, ReportQuery, RevisionConflict, StaleConfiguration, SubmitDiagnosticReport
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity, UnavailableSubject
from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered
from umbod.core.agent_behaviour.schema import DEDUPE_TABLE, REPORT_TABLE
from .conftest import Clock

pytestmark = pytest.mark.asyncio


async def test_first_publication_separates_criteria_from_collection(service: AgentBehaviourService, publication: PublishConfiguration) -> None:
    assert (await service.get_configuration()).revision == 1
    saved = await service.publish_configuration(publication)
    instructions = await service.get_instructions("task-review")
    assert saved.revision == 2
    assert instructions.patterns == publication.patterns
    assert instructions.playbook.collection_instructions == publication.playbooks[0].collection_instructions
    assert "Never send full transcripts" in instructions.reporting_guidance


async def test_concurrent_publication_does_not_overwrite_winner(service: AgentBehaviourService, publication: PublishConfiguration) -> None:
    results = await asyncio.gather(service.publish_configuration(publication), service.publish_configuration(publication), return_exceptions=True)
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1
    assert (await service.get_configuration()).revision == 2


async def test_invalid_reference_is_atomic(service: AgentBehaviourService, publication: PublishConfiguration) -> None:
    invalid = publication.model_copy(update={"patterns": ()})
    with pytest.raises(ConfigurationInvalid):
        await service.publish_configuration(invalid)
    assert (await service.get_configuration()).revision == 1


async def test_disabled_pattern_retains_membership_but_cannot_be_assessed(service: AgentBehaviourService, publication: PublishConfiguration) -> None:
    command = publication.model_copy(update={"patterns": (publication.patterns[0].model_copy(update={"enabled": False}),)})
    saved = await service.publish_configuration(command)
    assert saved.playbooks == publication.playbooks
    with pytest.raises(InstructionsUnavailable):
        await service.get_instructions("task-review")


async def test_reads_and_instruction_resolution_do_not_create_reports(service: AgentBehaviourService, publication: PublishConfiguration) -> None:
    await service.publish_configuration(publication)
    await service.get_instructions("task-review")
    assert (await service.list_reports(ReportQuery())).total == 0
    with pytest.raises(InstructionsUnavailable):
        await service.get_instructions("missing")


async def test_report_has_server_identity_and_original_snapshot(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport, clock: Clock) -> None:
    await service.publish_configuration(publication)
    receipt = await service.submit_report(caller, submission)
    await service.publish_configuration(publication.model_copy(update={"expected_revision": 2, "patterns": (), "playbooks": ()}))
    report = await service.get_report(receipt.report_id)
    assert report.caller == caller
    assert report.received_at == clock.now
    assert report.expires_at == clock.now + timedelta(days=30)
    assert report.instructions.patterns == publication.patterns
    assert report.instructions.configuration_revision == 2


async def test_exact_concurrent_retry_returns_one_report(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    receipts = await asyncio.gather(service.submit_report(caller, submission), service.submit_report(caller, submission))
    assert receipts[0].report_id == receipts[1].report_id
    assert sorted(receipt.duplicate for receipt in receipts) == [False, True]
    assert (await service.list_reports(ReportQuery())).total == 1


async def test_retry_is_resolved_before_current_configuration_validation(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    first = await service.submit_report(caller, submission)
    await service.publish_configuration(PublishConfiguration(expected_revision=2, patterns=(), playbooks=()))
    retried = await service.submit_report(caller, submission)
    assert retried.report_id == first.report_id
    assert retried.received_at == first.received_at
    assert retried.duplicate is True
    with pytest.raises(IdempotencyConflict):
        await service.submit_report(caller, submission.model_copy(update={"configuration_revision": 3}))


async def test_same_key_is_isolated_by_authenticated_issuer(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    other = CallerContext(authentication=caller.authentication, subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://other.invalid"), subject="user-a"))
    first = await service.submit_report(caller, submission)
    second = await service.submit_report(other, submission)
    assert first.report_id != second.report_id
    assert (await service.list_reports(ReportQuery())).total == 2


async def test_stale_or_proactive_submission_is_rejected_without_write(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    with pytest.raises(StaleConfiguration):
        await service.submit_report(caller, submission.model_copy(update={"configuration_revision": 3}))
    with pytest.raises(ProactiveDisabled):
        await service.submit_report(caller, submission.model_copy(update={"trigger": "proactive"}))
    with pytest.raises(ReportInvalid):
        await service.submit_report(caller, submission.model_copy(update={"assessments": ()}))
    assert (await service.list_reports(ReportQuery())).total == 0


async def test_unavailable_identity_cannot_submit(service: AgentBehaviourService, submission: SubmitDiagnosticReport) -> None:
    caller = CallerContext(authentication=AuthenticationProvenance.UNAVAILABLE, subject=UnavailableSubject(kind="unavailable"))
    with pytest.raises(CallerNotAuthorized):
        await service.submit_report(caller, submission)


async def test_manual_deletion_removes_prose_but_retains_tombstone(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport, database: Database) -> None:
    await service.publish_configuration(publication)
    receipt = await service.submit_report(caller, submission)
    await service.delete_report(receipt.report_id)
    await service.delete_report(receipt.report_id)
    with pytest.raises(ReportNotFound):
        await service.get_report(receipt.report_id)
    with pytest.raises(ReportGone):
        await service.submit_report(caller, submission)
    with pytest.raises(IdempotencyConflict):
        await service.submit_report(caller, submission.model_copy(update={"configuration_revision": 3}))
    async with database.read_session() as session:
        rows = await session.find_many(REPORT_TABLE, Query(NoFilter(), AllFields(), Unordered()))
        tombstones = await session.find_many(DEDUPE_TABLE, Query(NoFilter(), AllFields(), Unordered()))
    assert len(rows) == 0
    assert len(tombstones) == 1
    assert "context" not in tombstones[0].model_dump_json()
    assert "user-a" not in tombstones[0].model_dump_json()


async def test_exact_expiry_hides_report_and_cleanup_keeps_original_receipt(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport, clock: Clock) -> None:
    await service.publish_configuration(publication)
    receipt = await service.submit_report(caller, submission)
    clock.now += timedelta(days=30)
    assert (await service.list_reports(ReportQuery())).total == 0
    with pytest.raises(ReportNotFound):
        await service.get_report(receipt.report_id)
    assert await service.purge_expired() == 1
    assert (await service.submit_report(caller, submission)).report_id == receipt.report_id
    clock.now += timedelta(days=30)
    assert await service.purge_expired() == 1
    assert (await service.submit_report(caller, submission)).report_id != receipt.report_id


async def test_filters_apply_status_and_pattern_to_same_assessment(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    await service.submit_report(caller, submission)
    assert (await service.list_reports(ReportQuery(pattern_id="missing-context", status="observed"))).total == 1
    assert (await service.list_reports(ReportQuery(pattern_id="other", status="observed"))).total == 0
    assert (await service.list_reports(ReportQuery(status="not_assessed"))).total == 0


async def test_submission_rejects_extra_transcript_and_missing_assessment_summary(submission: SubmitDiagnosticReport) -> None:
    payload = submission.model_dump(mode="json")
    payload["transcript"] = "Forbidden"
    with pytest.raises(ValidationError):
        SubmitDiagnosticReport.model_validate(payload)
    payload.pop("transcript")
    payload["assessments"][0]["summary"] = " "
    with pytest.raises(ValidationError):
        SubmitDiagnosticReport.model_validate(payload)


async def test_unchanged_distinct_keys_are_distinct_reports(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    first = await service.submit_report(caller, submission)
    second = await service.submit_report(caller, submission.model_copy(update={"idempotency_key": uuid4()}))
    assert first.report_id != second.report_id
