import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from umbod.core.agent_behaviour import AgentBehaviourService, BehaviourConfiguration, InstructionsUnavailable, ReportingDisabled, PublishConfiguration, ReportQuery, RevisionConflict, SubmitDiagnosticReport
from umbod.core.agent_behaviour.schema import CONFIGURATION_TABLE, ConfigurationKey, ConfigurationRow
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.callers import CallerContext
from umbod.core.persistence import Database, DatabaseSession, ReadSession, Table, TransactionMode, UpsertCommand

from .conftest import Clock

pytestmark = pytest.mark.asyncio


class CountingDatabase:
    def __init__(self, database: Database) -> None:
        self._database = database
        self.writes = 0

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        await self._database.ensure_schema(tables)

    def read_session(self) -> AbstractAsyncContextManager[ReadSession]:
        return self._database.read_session()

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        self.writes += 1
        async with self._database.session(mode=mode) as session:
            yield session


class PausedFirstReadDatabase(CountingDatabase):
    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.read_finished = asyncio.Event()
        self.resume = asyncio.Event()

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        async with self._database.read_session() as session:
            yield session
        self.read_finished.set()
        await self.resume.wait()


async def test_publication_between_initial_read_and_seed_write_is_not_overwritten(database: Database, publication: PublishConfiguration) -> None:
    paused = PausedFirstReadDatabase(database)
    reader = DatabaseAgentBehaviourStore(paused)
    task = asyncio.create_task(reader.get_configuration())
    try:
        await asyncio.wait_for(paused.read_finished.wait(), timeout=2)
        saved = await DatabaseAgentBehaviourStore(database).publish_configuration(publication)
        paused.resume.set()
        assert await asyncio.wait_for(task, timeout=2) == saved
        assert await DatabaseAgentBehaviourStore(database).get_configuration() == saved
    finally:
        paused.resume.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_existing_default_reads_use_read_fast_path_without_reseeding(database: Database) -> None:
    counted = CountingDatabase(database)
    first = DatabaseAgentBehaviourStore(counted)
    defaults = await first.get_configuration()
    assert counted.writes == 1
    second = DatabaseAgentBehaviourStore(counted)
    assert await second.get_configuration() == defaults
    assert await first.get_configuration() == defaults
    assert counted.writes == 1


async def test_reading_recommendations_does_not_initialize_configuration(database: Database, clock: Clock) -> None:
    counted = CountingDatabase(database)
    service = AgentBehaviourService(DatabaseAgentBehaviourStore(counted), clock, uuid4)
    defaults = service.get_defaults()
    assert counted.writes == 0
    assert await service.get_configuration() == defaults
    assert counted.writes == 1


async def test_first_reads_seed_saved_default_settings_with_reporting_off(service: AgentBehaviourService, database: Database, clock: Clock) -> None:
    first = await service.get_configuration()
    second = AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4)
    assert await second.get_configuration() == first == service.get_defaults()
    assert first.revision == 1
    assert {pattern.id for pattern in first.patterns} == {"missing-context", "tool-problems", "task-blocked", "user-correction"}
    assert len(first.patterns) == 4
    assert all(pattern.enabled for pattern in first.patterns)
    assert all(pattern.assessment_prompt == pattern.description for pattern in first.patterns)
    assert len(first.playbooks) == 1
    assert first.playbooks[0].id == "behaviour-review"
    assert first.playbooks[0].enabled is True
    assert first.reporting_enabled is False
    with pytest.raises(ReportingDisabled):
        await second.get_instructions("behaviour-review")
    assert (await second.list_reports(ReportQuery())).total == 0


async def test_default_catalog_is_immutable(service: AgentBehaviourService) -> None:
    catalog = service.get_defaults()
    with pytest.raises(ValidationError):
        catalog.revision = 99
    with pytest.raises(ValidationError):
        catalog.patterns[0].enabled = False
    with pytest.raises(ValidationError):
        catalog.reporting_enabled = True
    assert service.get_defaults() == catalog


@pytest.mark.parametrize("change", ["remove", "edit", "disable", "empty"])
async def test_saved_default_customization_survives_new_store(service: AgentBehaviourService, database: Database, clock: Clock, change: str) -> None:
    defaults = await service.get_configuration()
    patterns = defaults.patterns
    playbooks = defaults.playbooks
    if change == "remove":
        patterns = patterns[1:]
        playbooks = (playbooks[0].model_copy(update={"pattern_ids": tuple(pattern.id for pattern in patterns)}),)
    elif change == "edit":
        patterns = (patterns[0].model_copy(update={"assessment_prompt": "Assess the administrator's revised criteria"}), *patterns[1:])
        playbooks = (playbooks[0].model_copy(update={"collection_instructions": "Use the administrator's revised collection instructions"}),)
    elif change == "disable":
        patterns = tuple(pattern.model_copy(update={"enabled": False}) for pattern in patterns)
        playbooks = (playbooks[0].model_copy(update={"enabled": False}),)
    else:
        patterns = ()
        playbooks = ()
    saved = await service.publish_configuration(PublishConfiguration(reporting_enabled=True, expected_revision=1, patterns=patterns, playbooks=playbooks))
    restarted = AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4)
    assert await restarted.get_configuration() == saved
    assert saved.revision == 2
    assert restarted.get_defaults() == defaults
    if change in {"disable", "empty"}:
        with pytest.raises(InstructionsUnavailable):
            await restarted.get_instructions("behaviour-review")


async def test_first_publication_rejects_pre_default_revision(service: AgentBehaviourService, publication: PublishConfiguration) -> None:
    with pytest.raises(RevisionConflict) as captured:
        await service.publish_configuration(publication.model_copy(update={"expected_revision": 0}))
    assert captured.value.current == service.get_defaults()
    assert await service.get_configuration() == service.get_defaults()


@pytest.mark.parametrize("trigger,revision", [("proactive", 1), ("user_requested", 2)])
async def test_first_default_submission_is_blocked_without_report(service: AgentBehaviourService, caller: CallerContext, trigger: str, revision: int) -> None:
    command = SubmitDiagnosticReport.model_validate({"idempotency_key": str(uuid4()), "configuration_revision": revision, "playbook_id": "behaviour-review", "trigger": trigger, "assessments": [{"pattern_id": pattern.id, "status": "not_assessed", "summary": "Context is unavailable", "evidence": []} for pattern in service.get_defaults().patterns]})
    with pytest.raises(ReportingDisabled):
        await service.submit_report(caller, command)
    assert (await service.list_reports(ReportQuery())).total == 0
    assert await service.get_configuration() == service.get_defaults()


@pytest.mark.parametrize("revision", [0, 1, 7])
async def test_existing_empty_configuration_is_never_reseeded(database: Database, clock: Clock, revision: int) -> None:
    persisted = BehaviourConfiguration(revision=revision, reporting_enabled=True, patterns=(), playbooks=())
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(CONFIGURATION_TABLE, UpsertCommand(key=ConfigurationKey(singleton=1), row=ConfigurationRow(singleton=1, configuration=persisted)))
    service = AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4)
    assert await service.get_configuration() == persisted
    with pytest.raises(InstructionsUnavailable):
        await service.get_instructions("behaviour-review")
    assert await service.get_configuration() == persisted


async def test_concurrent_instances_first_reads_and_publication_preserve_custom_configuration(database: Database, clock: Clock, publication: PublishConfiguration) -> None:
    services = tuple(AgentBehaviourService(DatabaseAgentBehaviourStore(database), clock, uuid4) for _ in range(8))
    results = await asyncio.gather(*(service.get_configuration() for service in services), services[0].publish_configuration(publication))
    saved = results[-1]
    assert saved.revision == 2
    assert saved.patterns == publication.patterns
    assert all(configuration.revision in {1, 2} for configuration in results)
    assert all(configuration == saved for configuration in await asyncio.gather(*(service.get_configuration() for service in services)))
