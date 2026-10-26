from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from umbod.config import AppConfig
from umbod.core.filesystem.administration import (
    PolicyConflict, PolicyRevisionConflict, RootGroupPolicyManagement,
    RootGroupPolicyView, SaveRootGroupPolicy,
)
from umbod.rest.authentication.local import LOCAL_DEVELOPMENT_ISSUER, local_rest_identity_enabled
from umbod.rest.instance_configuration.dependencies import get_app_config
from .deps import get_root_group_policy_management
from .models import RootAccessResponse


def policy_error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"detail": {"code": code, "message": "Filesystem policy request failed."}},
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


def response_view(view: RootGroupPolicyView, config: AppConfig) -> RootAccessResponse:
    return RootAccessResponse(
        **view.model_dump(), suggested_issuer=(
            LOCAL_DEVELOPMENT_ISSUER if local_rest_identity_enabled(config) else config.oidc.issuer_url
        ),
        group_claim=config.mcp.permission_group_claim,
    )


@router.get("/root-access")
async def inspect_root_access(
    management: Annotated[RootGroupPolicyManagement, Depends(get_root_group_policy_management)],
    config: Annotated[AppConfig, Depends(get_app_config)],
) -> RootAccessResponse:
    return response_view(await management.inspect(), config)


@router.put("/root-access")
async def save_root_access(
    command: SaveRootGroupPolicy,
    management: Annotated[RootGroupPolicyManagement, Depends(get_root_group_policy_management)],
    config: Annotated[AppConfig, Depends(get_app_config)],
) -> RootAccessResponse:
    return response_view(await management.save(command), config)
