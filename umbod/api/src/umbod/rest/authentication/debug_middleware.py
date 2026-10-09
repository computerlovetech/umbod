import logging

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class AdminAuthenticationDebugMiddleware:
    def __init__(
        self, app: ASGIApp, jwt_header_name: str, profile_header_name: str
    ) -> None:
        self.app = app
        self.jwt_header_name = jwt_header_name
        self.profile_header_name = profile_header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        payload = {
            "configured_access_header_present": self.jwt_header_name in request.headers,
            "configured_profile_header_present": self.profile_header_name
            in request.headers,
            "authorization_header_present": "authorization" in request.headers,
            "cookie_header_present": "cookie" in request.headers,
        }
        logger.warning("Admin authentication debug presence", extra=payload)
        await self.app(scope, receive, send)
