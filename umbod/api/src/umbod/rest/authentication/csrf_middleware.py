from collections.abc import Sequence
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


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
