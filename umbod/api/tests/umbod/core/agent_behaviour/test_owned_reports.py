from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from umbod.core.agent_behaviour import (
    AgentBehaviourService,
    CallerNotAuthorized,
    PublishConfiguration,
    ReportNotFound,
    ReportQuery,
    SubmitDiagnosticReport,
)
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity

from .conftest import Clock


@pytest_asyncio.fixture
async def populated_reports(
    service: AgentBehaviourService, publication: PublishConfiguration,
    caller: CallerContext, submission: SubmitDiagnosticReport, clock: Clock,
) -> tuple[UUID, UUID, UUID, UUID]:
    await service.publish_configuration(publication)
    owners = (
        caller,
        caller,
        CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="https://other.identity.invalid"), subject="user-a",
        )),
        CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="https://identity.invalid"), subject="user-b",
        )),
    )
    report_ids: list[UUID] = []
    for owner in owners:
        clock.now += timedelta(seconds=1)
        receipt = await service.submit_report(owner, submission.model_copy(update={"idempotency_key": uuid4()}))
        report_ids.append(receipt.report_id)
    older, newer, other_issuer, other_subject = report_ids
    return older, newer, other_issuer, other_subject


@pytest.mark.asyncio
@pytest.mark.parametrize("offset,index", [(0, 1), (1, 0), (2, -1)])
async def test_owner_scope_precedes_total_and_pagination(
    service: AgentBehaviourService, caller: CallerContext,
    populated_reports: tuple[UUID, UUID, UUID, UUID], offset: int, index: int,
) -> None:
    page = await service.list_owned_reports(caller, ReportQuery(limit=1, offset=offset, status="observed"))

    assert page.total == 2
    assert tuple(item.report_id for item in page.items) == ((populated_reports[index],) if index >= 0 else ())


@pytest.mark.asyncio
async def test_owned_detail_distinguishes_neither_foreign_issuer_nor_foreign_subject_from_missing(
    service: AgentBehaviourService, caller: CallerContext, populated_reports: tuple[UUID, UUID, UUID, UUID],
) -> None:
    older, _, other_issuer, other_subject = populated_reports
    assert await service.get_owned_report(caller, older) == await service.get_report(older)
    for report_id in (other_issuer, other_subject, uuid4()):
        with pytest.raises(ReportNotFound):
            await service.get_owned_report(caller, report_id)


@pytest.mark.asyncio
async def test_owned_reads_hide_expired_rows_before_purge(
    service: AgentBehaviourService, publication: PublishConfiguration,
    caller: CallerContext, submission: SubmitDiagnosticReport, clock: Clock,
) -> None:
    await service.publish_configuration(publication)
    receipt = await service.submit_report(caller, submission)
    clock.now += timedelta(days=30)

    assert (await service.list_owned_reports(caller, ReportQuery())).total == 0
    with pytest.raises(ReportNotFound):
        await service.get_owned_report(caller, receipt.report_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.LOCAL_SEMANTIC,
    AuthenticationProvenance.LOCAL_SIMULATION,
    AuthenticationProvenance.LOCAL_TEST,
])
async def test_nonverified_reader_cannot_use_same_identity_to_access_reports(
    service: AgentBehaviourService, caller: CallerContext, provenance: AuthenticationProvenance,
) -> None:
    untrusted = CallerContext(authentication=provenance, subject=caller.subject)

    with pytest.raises(CallerNotAuthorized):
        await service.list_owned_reports(untrusted, ReportQuery())
