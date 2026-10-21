from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class PersonalOAuthValidationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()
        personal_write = (
            self.path.endswith("/personal-oauth")
            and bool(self.methods & {"POST", "PUT"})
        )

        async def sanitized_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                if not personal_write:
                    raise
                return JSONResponse(
                    status_code=422,
                    content={"detail": {"code": "invalid_personal_oauth_configuration"}},
                )

        return sanitized_handler
