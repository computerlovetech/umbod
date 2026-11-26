from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from umbod.core.system_settings import (
    SettingsPermissionDenied,
    SettingsStorageUnavailable,
)

from umbod.rest.authentication.deps import ADMIN_AUTHORIZED_STATE_KEY


class SystemSettingsRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                if getattr(request.state, ADMIN_AUTHORIZED_STATE_KEY, False) is not True:
                    raise HTTPException(status_code=401, detail="Unauthorized")
                response = await handler(request)
            except SettingsPermissionDenied:
                response = JSONResponse(
                    status_code=403, content={"detail": "Forbidden"}
                )
            except SettingsStorageUnavailable:
                response = JSONResponse(
                    status_code=503,
                    content={"detail": {"code": "system_settings_unavailable"}},
                )
            except RequestValidationError as error:
                response = JSONResponse(
                    status_code=422,
                    content={
                        "detail": [
                            {
                                "loc": issue["loc"][:-1]
                                if issue["type"] == "extra_forbidden"
                                else issue["loc"],
                                "type": issue["type"],
                                "msg": "Invalid settings request",
                            }
                            for issue in error.errors()
                        ]
                    },
                )
            except HTTPException as error:
                if error.status_code == 400 and isinstance(
                    error.__cause__, UnicodeDecodeError
                ):
                    response = JSONResponse(
                        status_code=422,
                        content={
                            "detail": [
                                {
                                    "loc": ["body"],
                                    "type": "json_invalid",
                                    "msg": "Invalid settings request",
                                }
                            ]
                        },
                    )
                else:
                    response = await http_exception_handler(request, error)
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle
