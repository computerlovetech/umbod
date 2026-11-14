from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from umbod.core.filesystem.namespaces.errors import NamespaceValidationError
from umbod.core.filesystem.namespaces import CreateSharedNamespace, SaveSharedNamespace, SaveSharedNamespaceDescription, SharedNamespaceView, NamespaceManagement

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from umbod.core.filesystem.errors import PolicyConflict, PolicyRevisionConflict, PolicyUnavailable
from .deps import get_namespace_management


def policy_error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"detail": {"code": code, "message": "Filesystem policy configuration unavailable." if status == 503 else "Filesystem policy request failed."}},
        headers={"Cache-Control": "no-store"},
    )


class PolicyRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await handler(request)
            except PolicyRevisionConflict:
                return policy_error(409, "filesystem_policy_stale")
            except PolicyUnavailable:
                return policy_error(503, "filesystem_policy_unavailable")
            except PolicyConflict:
                return policy_error(409, "filesystem_policy_conflict")
            except (RequestValidationError, NamespaceValidationError):
                return policy_error(422, "filesystem_policy_invalid")
            except Exception:
                return policy_error(500, "filesystem_policy_storage_failure")
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(prefix="/filesystem", tags=["filesystem-administration"], route_class=PolicyRoute)


@router.get("/namespaces")
async def list_namespaces(
    management: Annotated[NamespaceManagement, Depends(get_namespace_management)],
) -> dict[str, list[SharedNamespaceView]]:
    return {"namespaces": await management.list()}


@router.post("/namespaces", status_code=201)
async def create_namespace(
    command: CreateSharedNamespace,
    management: Annotated[NamespaceManagement, Depends(get_namespace_management)],
) -> SharedNamespaceView:
    return await management.create(command)


@router.put("/namespaces/{namespace_id}")
async def save_namespace(
    namespace_id: UUID, command: SaveSharedNamespace | SaveSharedNamespaceDescription,
    management: Annotated[NamespaceManagement, Depends(get_namespace_management)],
) -> SharedNamespaceView:
    return await management.save(namespace_id, command)
