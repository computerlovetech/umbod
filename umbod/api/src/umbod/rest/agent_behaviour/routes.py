from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from umbod.core.agent_behaviour import (
    AgentBehaviourService,
    BehaviourConfiguration,
    ConfigurationInvalid,
    DiagnosticReport,
    PublishConfiguration,
    ReportNotFound,
    ReportPage,
    ReportQuery,
    RevisionConflict,
    StorageUnavailable,
)

from .dependencies import get_agent_behaviour_service


class AgentBehaviourRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await handler(request)
            except RevisionConflict as error:
                response = JSONResponse(status_code=409, content={"detail": {"code": error.code, "current": error.current.model_dump(mode="json")}})
            except ConfigurationInvalid as error:
                response = JSONResponse(status_code=422, content={"detail": {"code": error.code, "issues": [issue.model_dump(mode="json") for issue in error.issues]}})
            except ReportNotFound as error:
                response = JSONResponse(status_code=404, content={"detail": {"code": error.code}})
            except StorageUnavailable as error:
                response = JSONResponse(status_code=503, content={"detail": {"code": error.code}})
            except RequestValidationError as error:
                issues = [{"path": ".".join(str(part) for part in (issue["loc"][:-1] if issue["type"] == "extra_forbidden" else issue["loc"]))[:200], "code": issue["type"]} for issue in error.errors()[:50]]
                response = JSONResponse(status_code=422, content={"detail": {"code": "validation_error", "issues": issues}})
            except HTTPException as error:
                response = JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)
            except Exception:
                response = JSONResponse(status_code=500, content={"detail": {"code": "internal_server_error"}})
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(prefix="/agent-behaviour", tags=["agent-behaviour"], route_class=AgentBehaviourRoute)
AgentBehaviourDependency = Annotated[AgentBehaviourService, Depends(get_agent_behaviour_service)]


@router.get("/defaults")
async def get_defaults(service: AgentBehaviourDependency) -> BehaviourConfiguration:
    return service.get_defaults()


@router.get("/configuration")
async def get_configuration(service: AgentBehaviourDependency) -> BehaviourConfiguration:
    return await service.get_configuration()


@router.put("/configuration")
async def publish_configuration(command: PublishConfiguration, service: AgentBehaviourDependency) -> BehaviourConfiguration:
    return await service.publish_configuration(command)


@router.get("/reports")
async def list_reports(service: AgentBehaviourDependency, query: Annotated[ReportQuery, Query()]) -> ReportPage:
    return await service.list_reports(query)


@router.get("/reports/{report_id}")
async def get_report(report_id: UUID, service: AgentBehaviourDependency) -> DiagnosticReport:
    return await service.get_report(report_id)


@router.delete("/reports/{report_id}", status_code=204)
async def delete_report(report_id: UUID, service: AgentBehaviourDependency) -> Response:
    await service.delete_report(report_id)
    return Response(status_code=204)
