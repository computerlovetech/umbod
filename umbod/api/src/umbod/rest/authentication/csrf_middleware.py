from collections.abc import Sequence
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from umbod.rest.authentication.rest_paths import protected_rest_request


class AdminCookieCsrfMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, site_base_url: str, allowed_origins: Sequence[str]
    ) -> None:
        super().__init__(app)
        site = urlsplit(site_base_url)
        site_origin = f"{site.scheme}://{site.netloc}"
        self.allowed_origins = frozenset(
            origin for origin in (site_origin, *allowed_origins)
            if origin not in ("*", "null", "")
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in ("GET", "HEAD", "OPTIONS") and "cookie" in request.headers:
            if (
                request.headers.get("origin") not in self.allowed_origins
                or request.headers.get("x-umbod-web-request") != "1"
            ):
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        return await call_next(request)


class RestCookieCsrfMiddleware(AdminCookieCsrfMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not protected_rest_request(request.scope):
            return await call_next(request)
        response = await super().dispatch(request, call_next)
        if response.status_code == 403:
            response.headers["Cache-Control"] = "no-store"
        return response
