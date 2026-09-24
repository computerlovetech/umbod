import base64
import json
import logging

from typing import Any

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from umbod.rest.authentication.tokens import extract_jwt_header_token

logger = logging.getLogger(__name__)


class AdminAuthenticationDebugMiddleware:
    def __init__(self, app: ASGIApp, jwt_header_name: str) -> None:
        self.app = app
        self.jwt_header_name = jwt_header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        self._log_request(request)
        await self.app(scope, receive, send)

    def _log_request(self, request: Request) -> None:
        configured_header_value = request.headers.get(self.jwt_header_name, "")
        authorization_header_value = request.headers.get("authorization", "")
        token = extract_jwt_header_token(configured_header_value)
        payload = {
            "method": request.method,
            "path": request.url.path,
            "headers": dict(request.headers),
            "configured_jwt_header_name": self.jwt_header_name,
            "configured_jwt_header_present": bool(configured_header_value),
            "authorization_header_present": bool(authorization_header_value),
            "extracted_token_present": bool(token),
            "extracted_token_header": _decode_jwt_part(token, 0),
            "extracted_token_payload": _decode_jwt_part(token, 1),
        }
        logger.warning(
            "Admin auth debug context %s",
            json.dumps(payload, default=str, sort_keys=True),
            extra=payload,
        )


def _decode_jwt_part(token: str, index: int) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) <= index:
        return None
    value = parts[index]
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{value}{padding}")
        data = json.loads(decoded.decode("utf-8"))
    except ValueError, json.JSONDecodeError, UnicodeDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None
