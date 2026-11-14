from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import uuid4

import pytest
from pydantic import BaseModel

from umbod.core.agent_behaviour import AgentBehaviourService, PublishConfiguration, ReportQuery, StorageUnavailable, SubmitDiagnosticReport
from umbod.core.agent_behaviour.store import DatabaseAgentBehaviourStore
from umbod.core.callers import CallerContext
from umbod.core.persistence import Database, DatabaseSession, ReadSession, Table, TransactionMode
from .conftest import Clock


class LostAcknowledgementDatabase:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def ensure_schema(self, tables: Sequence[Table[BaseModel, BaseModel]]) -> None:
        await self._database.ensure_schema(tables)

    def read_session(self) -> AbstractAsyncContextManager[ReadSession]:
        return self._database.read_session()

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with self._database.session(mode=mode) as session:
            yield session
        raise RuntimeError("private persistence details")


@pytest.mark.asyncio
async def test_lost_commit_acknowledgement_is_safely_deduplicated_on_retry(database: Database, service: AgentBehaviourService, clock: Clock, publication: PublishConfiguration, caller: CallerContext, submission: SubmitDiagnosticReport) -> None:
    await service.publish_configuration(publication)
    lossy = AgentBehaviourService(DatabaseAgentBehaviourStore(LostAcknowledgementDatabase(database)), clock, uuid4)
    with pytest.raises(StorageUnavailable) as captured:
        await lossy.submit_report(caller, submission)
    assert str(captured.value) == "storage_unavailable"
    receipt = await service.submit_report(caller, submission)
    assert receipt.duplicate is True
    assert (await service.list_reports(ReportQuery())).total == 1
