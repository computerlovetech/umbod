from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class PersonalConfigurationValidationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()
        error_code = next((code for suffix, code in (
            ("/personal-oauth", "invalid_personal_oauth_configuration"),
            ("/personal-tools", "invalid_personal_tool_configuration"),
        ) if self.path.endswith(suffix)), "")
        personal_write = bool(error_code) and bool(self.methods & {"POST", "PUT"})

        async def sanitized_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                if not personal_write:
                    raise
                return JSONResponse(
                    status_code=422,
                    content={"detail": {"code": error_code}},
                )

        return sanitized_handler
