from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from umbod.core.callers import CallerContext
from .defaults import get_default_configuration
from .models import BehaviourConfiguration, DiagnosticInstructions, DiagnosticReceipt, DiagnosticReport, PublishConfiguration, ReportPage, ReportQuery, SubmitDiagnosticReport
from .policy import resolve_instructions, validate_caller, validate_report_reader
from .ports import AgentBehaviourStore


class AgentBehaviourService:
    def __init__(self, store: AgentBehaviourStore, clock: Callable[[], datetime], new_id: Callable[[], UUID]) -> None:
        self._store = store
        self._clock = clock
        self._new_id = new_id

    def get_defaults(self) -> BehaviourConfiguration:
        return get_default_configuration()

    async def get_configuration(self) -> BehaviourConfiguration:
        return await self._store.get_configuration()

    async def publish_configuration(self, command: PublishConfiguration) -> BehaviourConfiguration:
        return await self._store.publish_configuration(command)

    async def get_instructions(self, playbook_id: str) -> DiagnosticInstructions:
        return resolve_instructions(await self._store.get_configuration(), playbook_id)

    async def submit_report(self, caller: CallerContext, command: SubmitDiagnosticReport) -> DiagnosticReceipt:
        validate_caller(caller)
        return await self._store.submit_report(caller, command, self._clock(), self._new_id())

    async def list_reports(self, query: ReportQuery) -> ReportPage:
        return await self._store.list_reports(query, self._clock())

    async def get_report(self, report_id: UUID) -> DiagnosticReport:
        return await self._store.get_report(report_id, self._clock())

    async def list_owned_reports(self, caller: CallerContext, query: ReportQuery) -> ReportPage:
        return await self._store.list_owned_reports(validate_report_reader(caller), query, self._clock())

    async def get_owned_report(self, caller: CallerContext, report_id: UUID) -> DiagnosticReport:
        return await self._store.get_owned_report(validate_report_reader(caller), report_id, self._clock())

    async def delete_report(self, report_id: UUID) -> None:
        await self._store.delete_report(report_id, self._clock())

    async def purge_expired(self) -> int:
        return await self._store.purge_expired(self._clock(), 100)

