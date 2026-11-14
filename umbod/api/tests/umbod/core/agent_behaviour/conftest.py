from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.agent_behaviour import AgentBehaviourService, BehaviourPattern, DiagnosticPlaybook, PatternAssessment, PublishConfiguration, SubmitDiagnosticReport
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.callers import AuthenticationProvenance, CallerContext, DeclaredIssuer, SubjectIdentity
from umbod.core.persistence import Database


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 1, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime.database
    finally:
        await runtime.shutdown()


@pytest.fixture
def service(database: Database, clock: Clock) -> AgentBehaviourService:
    return AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4)


@pytest.fixture
def caller() -> CallerContext:
    return CallerContext(authentication=AuthenticationProvenance.UPSTREAM_VERIFIED, subject=SubjectIdentity(issuer=DeclaredIssuer(value="https://identity.invalid"), subject="user-a"))


@pytest.fixture
def publication() -> PublishConfiguration:
    pattern = BehaviourPattern(id="missing-context", name="Missing context", description="Necessary context is missing", assessment_prompt="Assess whether task context is missing", inclusion_criteria="Blocked on unavailable information", exclusion_criteria="Ordinary clarification", categories=("quality",), polarity="negative", enabled=True)
    playbook = DiagnosticPlaybook(id="task-review", name="Task review", collection_instructions="Review authorized context and report facts", pattern_ids=(pattern.id,), enabled=True, allow_proactive=False)
    return PublishConfiguration(expected_revision=1, patterns=(pattern,), playbooks=(playbook,))


@pytest.fixture
def submission() -> SubmitDiagnosticReport:
    return SubmitDiagnosticReport(idempotency_key=uuid4(), configuration_revision=2, playbook_id="task-review", trigger="user_requested", assessments=(PatternAssessment(pattern_id="missing-context", status="observed", summary="Task context was unavailable", evidence=("A required specification was unavailable",)),))
