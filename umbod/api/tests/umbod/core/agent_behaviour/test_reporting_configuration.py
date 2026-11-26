from uuid import uuid4

import pytest

from umbod.core.agent_behaviour import AgentBehaviourService, ConfigurationInvalid, DiagnosticPlaybook, InstructionsUnavailable, PatternAssessment, PublishConfiguration, SubmitDiagnosticReport, available_playbooks
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.callers import CallerContext
from umbod.core.persistence import Database

from .conftest import Clock

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("remove", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_dormant_reporting_preferences_and_memberships_survive_reload(service: AgentBehaviourService, database: Database, clock: Clock, remove: bool, enabled: bool) -> None:
    defaults = await service.get_configuration()
    custom = DiagnosticPlaybook(id="custom-review", name="Custom review", collection_instructions="Preserve my collection instructions", pattern_ids=("missing-context",), enabled=enabled)
    settings = (defaults.playbooks[0], custom)
    saved = await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=1, patterns=defaults.patterns, playbooks=settings))
    patterns = tuple(pattern for pattern in saved.patterns if pattern.id != "missing-context") if remove else tuple(pattern.model_copy(update={"enabled": False}) if pattern.id == "missing-context" else pattern for pattern in saved.patterns)
    dormant = await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=2, patterns=patterns, playbooks=settings))
    restarted = AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4)
    assert await restarted.get_configuration() == dormant
    assert dormant.playbooks == settings
    assert [item.id for item in available_playbooks(dormant)] == ["behaviour-review"]
    assert (await restarted.get_instructions("behaviour-review")).playbook.pattern_ids == ("tool-problems", "task-blocked", "user-correction")
    with pytest.raises(InstructionsUnavailable):
        await restarted.get_instructions("custom-review")
    restored = await restarted.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=3, patterns=defaults.patterns, playbooks=dormant.playbooks))
    assert restored.playbooks == settings
    assert (await restarted.get_instructions("behaviour-review")).playbook.pattern_ids == defaults.playbooks[0].pattern_ids
    if enabled:
        assert (await restarted.get_instructions("custom-review")).playbook == custom
    else:
        with pytest.raises(InstructionsUnavailable):
            await restarted.get_instructions("custom-review")


async def test_removing_every_pattern_preserves_instructions_without_available_reporting(service: AgentBehaviourService, database: Database, clock: Clock) -> None:
    defaults = await service.get_configuration()
    configured = defaults.playbooks[0].model_copy(update={"collection_instructions": "Keep these customized instructions", "enabled": False})
    empty = await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=1, patterns=(), playbooks=(configured,)))
    restarted = AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4)
    assert await restarted.get_configuration() == empty
    assert available_playbooks(empty) == ()
    restored = await restarted.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=2, patterns=defaults.patterns, playbooks=empty.playbooks))
    assert restored.playbooks == (configured,)
    assert available_playbooks(restored) == ()


async def test_new_unknown_membership_is_rejected_but_retired_membership_can_be_kept(service: AgentBehaviourService) -> None:
    defaults = await service.get_configuration()
    dormant = await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=1, patterns=(), playbooks=defaults.playbooks))
    invented = dormant.playbooks[0].model_copy(update={"pattern_ids": ("unknown-pattern",)})
    with pytest.raises(ConfigurationInvalid):
        await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=2, patterns=(), playbooks=(invented,)))
    another = dormant.playbooks[0].model_copy(update={"id": "new-reporting-settings"})
    with pytest.raises(ConfigurationInvalid):
        await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=2, patterns=(), playbooks=(another,)))
    assert await service.get_configuration() == dormant


async def test_report_requires_only_resolved_active_memberships(service: AgentBehaviourService, caller: CallerContext) -> None:
    defaults = await service.get_configuration()
    patterns = tuple(pattern.model_copy(update={"enabled": False}) if pattern.id == "missing-context" else pattern for pattern in defaults.patterns)
    saved = await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=1, patterns=patterns, playbooks=defaults.playbooks))
    instructions = await service.get_instructions("behaviour-review")
    command = SubmitDiagnosticReport(idempotency_key=uuid4(), configuration_revision=saved.revision, playbook_id="behaviour-review", trigger="user_requested", assessments=tuple(PatternAssessment(pattern_id=pattern.id, status="not_assessed", summary="No authorized context", evidence=()) for pattern in instructions.patterns))
    receipt = await service.submit_report(caller, command)
    report = await service.get_report(receipt.report_id)
    assert report.instructions == instructions
    assert len(report.instructions.patterns) == 3
    assert saved.playbooks[0].pattern_ids == defaults.playbooks[0].pattern_ids
