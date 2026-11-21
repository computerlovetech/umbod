from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class BoundedPreviewRoute(APIRoute):
    @staticmethod
    def invalid_input_detail() -> dict[str, str]:
        return {"code": "invalid_preview_input"}

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            headers = {"Cache-Control": "no-store"}
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 12288:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": self.invalid_input_detail()},
                        headers=headers,
                    )
                body.extend(chunk)
            request._body = bytes(body)
            try:
                response = await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": self.invalid_input_detail()},
                    headers=headers,
                )
            except HTTPException as error:
                error.headers = {**(error.headers or {}), **headers}
                raise
            response.headers.update(headers)
            return response

        return bounded_handler
