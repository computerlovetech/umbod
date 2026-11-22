from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from umbod.core.agent_behaviour import DiagnosticReport, ReportPage, ReportQuery
from umbod.core.callers import CallerContext
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims

from .routes import AgentBehaviourDependency, AgentBehaviourRoute


personal_router = APIRouter(
    prefix="/agent-behaviour",
    tags=["agent-behaviour"],
    route_class=AgentBehaviourRoute,
    dependencies=[Depends(get_verified_access_claims)],
)
ReportCaller = Annotated[CallerContext, Depends(get_caller_context)]


@personal_router.get("/reports")
async def list_owned_reports(
    caller: ReportCaller, service: AgentBehaviourDependency, query: Annotated[ReportQuery, Query()],
) -> ReportPage:
    return await service.list_owned_reports(caller, query)


@personal_router.get("/reports/{report_id}")
async def get_owned_report(report_id: UUID, caller: ReportCaller, service: AgentBehaviourDependency) -> DiagnosticReport:
    return await service.get_owned_report(caller, report_id)
