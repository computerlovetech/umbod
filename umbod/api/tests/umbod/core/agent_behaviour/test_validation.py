from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.agent_behaviour import AgentBehaviourService, BehaviourPattern, ConfigurationInvalid, DiagnosticPlaybook, PatternAssessment, PublishConfiguration, ReportQuery, SubmitDiagnosticReport
from umbod.core.callers import CallerContext


@pytest.mark.parametrize("status", ["observed", "not_assessed"])
def test_reported_or_unassessed_patterns_require_nonblank_summary(status: str) -> None:
    with pytest.raises(ValidationError):
        PatternAssessment.model_validate({"pattern_id": "task", "status": status, "summary": " ", "evidence": []})


def test_unassessed_pattern_cannot_include_invented_evidence() -> None:
    with pytest.raises(ValidationError):
        PatternAssessment(pattern_id="task", status="not_assessed", summary="Context is unavailable", evidence=("Unsupported assertion",))


def test_utf8_size_limit_is_enforced_before_persistence() -> None:
    payload = {"idempotency_key": str(uuid4()), "configuration_revision": 1, "playbook_id": "task", "trigger": "user_requested", "assessments": [{"pattern_id": f"pattern-{index}", "status": "observed", "summary": "界" * 1000, "evidence": []} for index in range(20)]}
    with pytest.raises(ValidationError, match="32 KiB"):
        SubmitDiagnosticReport.model_validate(payload)


@pytest.mark.parametrize("identifier", ["../secrets", "UPPERCASE", " spaced", "x" * 65])
def test_pattern_identifiers_cannot_escape_resource_namespace(identifier: str, publication: PublishConfiguration) -> None:
    payload = publication.patterns[0].model_dump()
    payload["id"] = identifier
    with pytest.raises(ValidationError):
        BehaviourPattern.model_validate(payload)


@pytest.mark.parametrize("filters", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"owner": "someone"}, {"status": "success"}])
def test_report_query_rejects_unbounded_or_unknown_inputs(filters: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReportQuery.model_validate(filters)


def test_playbooks_require_explicit_proactive_policy(publication: PublishConfiguration) -> None:
    payload = publication.playbooks[0].model_dump()
    del payload["allow_proactive"]
    with pytest.raises(ValidationError):
        DiagnosticPlaybook.model_validate(payload)


@pytest.mark.asyncio
async def test_assessment_reordering_is_the_same_idempotent_request(service: AgentBehaviourService, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    second_pattern = publication.patterns[0].model_copy(update={"id": "tool-gap"})
    playbook = publication.playbooks[0].model_copy(update={"pattern_ids": (publication.patterns[0].id, second_pattern.id)})
    await service.publish_configuration(publication.model_copy(update={"patterns": (*publication.patterns, second_pattern), "playbooks": (playbook,)}))
    command = submission.model_copy(update={"assessments": (*submission.assessments, PatternAssessment(pattern_id="tool-gap", status="not_assessed", summary="Tools were not assessed", evidence=()))})
    receipt = await service.submit_report(caller, command)
    duplicate = await service.submit_report(caller, command.model_copy(update={"assessments": tuple(reversed(command.assessments))}))
    assert duplicate.report_id == receipt.report_id
    assert duplicate.duplicate is True
    assert (await service.list_reports(ReportQuery(pattern_id="tool-gap", status="observed"))).total == 0
    assert (await service.list_reports(ReportQuery(pattern_id="tool-gap", status="not_assessed"))).total == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("condition,expected_path,expected_code", [("duplicate", "patterns.1.id", "duplicate_id"), ("unknown", "playbooks.0.pattern_ids.0", "unknown_pattern")])
async def test_invalid_configuration_identifies_safe_field_path(service: AgentBehaviourService, publication: PublishConfiguration, condition: str, expected_path: str, expected_code: str) -> None:
    changes: dict[str, dict[str, object]] = {
        "duplicate": {"patterns": publication.patterns * 2},
        "unknown": {"patterns": ()},
    }
    with pytest.raises(ConfigurationInvalid) as captured:
        await service.publish_configuration(publication.model_copy(update=changes[condition]))
    assert captured.value.issues[0].path == expected_path
    assert captured.value.issues[0].code == expected_code
    assert publication.patterns[0].description not in str(captured.value)
