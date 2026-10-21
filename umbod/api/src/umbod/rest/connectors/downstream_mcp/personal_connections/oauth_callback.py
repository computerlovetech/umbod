import re
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService

from .oauth_dependencies import get_personal_oauth_callback_service


CALLBACK_PATH = "/api/oauth/downstream-mcp/callback"
CALLBACK_QUERY_KEY = "personal_oauth_callback_parameters"
router = APIRouter()


def parse_callback_query(raw: bytes) -> dict[str, str]:
    if len(raw) > 16384 or re.search(rb"%(?![0-9A-Fa-f]{2})", raw):
        raise ValueError()
    pairs = parse_qsl(raw.decode("ascii"), keep_blank_values=True, strict_parsing=True,
                      max_num_fields=5, encoding="utf-8", errors="strict")
    parameters = dict(pairs)
    if len(parameters) != len(pairs) or set(parameters) - {"state", "code", "iss", "error", "scope"}:
        raise ValueError()
    if any((not value and key != "scope") or len(value) > 8192
           or any(ord(c) < 32 or ord(c) == 127 for c in value)
           for key, value in parameters.items()):
        raise ValueError()
    if not parameters.get("state") or (("code" in parameters) == ("error" in parameters)):
        raise ValueError()
    if "code" in parameters and not parameters.get("iss"):
        raise ValueError()
    return parameters


class PersonalOAuthQueryRedactionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        root_path = scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        callback_prefix = CALLBACK_PATH.rsplit("/", 1)[0]
        callback_namespace = path == callback_prefix or path.startswith(callback_prefix + "/")
        if scope["type"] == "http" and callback_namespace:
            raw = scope.get("query_string", b"")
            scope["query_string"] = b""
            parameters: dict[str, str] = {}
            try:
                parameters = parse_callback_query(raw)
            except (ValueError, UnicodeError):
                pass
            scope.setdefault("state", {})[CALLBACK_QUERY_KEY] = parameters
        try:
            await self.app(scope, receive, send)
        finally:
            if scope["type"] == "http" and callback_namespace:
                scope.get("state", {}).pop(CALLBACK_QUERY_KEY, None)


def callback_response(status_code: int) -> PlainTextResponse:
    return PlainTextResponse(
        "Authorization processed. You may close this window." if status_code == 200
        else "Authorization could not be completed. Start a new attempt.",
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/callback", response_class=PlainTextResponse)
async def personal_oauth_callback(
    request: Request,
    service: Annotated[PersonalOAuthCallbackService, Depends(get_personal_oauth_callback_service)],
) -> PlainTextResponse:
    parameters = getattr(request.state, CALLBACK_QUERY_KEY, {})
    if not parameters:
        return callback_response(400)
    try:
        await service.finish(
            parameters["state"], parameters.get("code", ""), parameters.get("iss", ""),
            parameters.get("error", ""), parameters.get("scope", ""),
        )
    except Exception:
        return callback_response(400)
    return callback_response(200)
