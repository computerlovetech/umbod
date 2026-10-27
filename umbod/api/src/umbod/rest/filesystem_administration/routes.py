from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from umbod.core.filesystem.administration import (
    PolicyConflict, PolicyRevisionConflict, PolicyUnavailable, RootGroupPolicyManagement,
    RootGroupPolicyView, SaveRootGroupPolicy,
)
from .deps import get_root_group_policy_management


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
            except RequestValidationError:
                return policy_error(422, "filesystem_policy_invalid")
            except Exception:
                return policy_error(500, "filesystem_policy_storage_failure")
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(prefix="/filesystem", tags=["filesystem-administration"], route_class=PolicyRoute)


@router.get("/root-access")
async def inspect_root_access(
    management: Annotated[RootGroupPolicyManagement, Depends(get_root_group_policy_management)],
) -> RootGroupPolicyView:
    return await management.inspect()


@router.put("/root-access")
async def save_root_access(
    command: SaveRootGroupPolicy,
    management: Annotated[RootGroupPolicyManagement, Depends(get_root_group_policy_management)],
) -> RootGroupPolicyView:
    return await management.save(command)
