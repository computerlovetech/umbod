import base64
import hashlib
import re
from html import escape
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import CallbackRoute, GenericRoute, IssuerRoute, MissingCallbackIssuer, PresentCallbackIssuer
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import FinishCallback
from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService

from .dependencies import Factories
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


def get_personal_oauth_return_destination(factories: Factories) -> str:
    return factories.settings.endpoints.site_base_url.rstrip("/") + "/dashboard"


def callback_response(status_code: int, return_destination: str) -> HTMLResponse:
    succeeded = status_code == 200
    title = "Sign-in complete" if succeeded else "Sign-in could not be completed"
    message = (
        "Authorization processed. Tools will be loaded in your dashboard."
        if succeeded else
        "Return to the dashboard and check the existing sign-in attempt. "
        "Cancel it or wait for expiry before trying again."
    )
    guidance = (
        "This window will try to close automatically. If it stays open, you may close it or return to Umbod."
        if succeeded else "You can close this window after returning to Umbod."
    )
    script = "try { window.opener = null; } catch {}"
    if succeeded:
        script += " setTimeout(() => { try { window.close(); } catch {} }, 1200);"
    style = (
        "body { margin: 0; padding: 2rem; background: #f5f5f4; color: #1c1917; "
        "font-family: system-ui, sans-serif; line-height: 1.6; } "
        "main { max-width: 32rem; margin: 10vh auto; padding: 2rem; "
        "background: white; border: 1px solid #d6d3d1; border-radius: 1rem; } "
        "h1 { line-height: 1.2; } a { color: #155e75; font-weight: 600; }"
    )
    script_hash = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    style_hash = base64.b64encode(hashlib.sha256(style.encode("utf-8")).digest()).decode("ascii")
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title} | Umbod</title><style>{style}</style></head>"
        f"<body><main><p>Umbod</p><h1>{title}</h1><p>{message}</p><p>{guidance}</p>"
        f'<a href="{escape(return_destination, quote=True)}" rel="noopener noreferrer">Return to Umbod</a>'
        f"</main><script>{script}</script></body></html>",
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; "
                f"script-src 'sha256-{script_hash}'; style-src 'sha256-{style_hash}'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/callback", response_class=HTMLResponse)
async def personal_oauth_callback(
    request: Request,
    service: Annotated[PersonalOAuthCallbackService, Depends(get_personal_oauth_callback_service)],
    return_destination: Annotated[str, Depends(get_personal_oauth_return_destination)],
) -> HTMLResponse:
    return await finish_callback(request, service, GenericRoute(kind="generic"), return_destination)


@router.get("/callback/issuer/{issuer_key}", response_class=HTMLResponse)
async def personal_oauth_issuer_callback(
    issuer_key: str,
    request: Request,
    service: Annotated[PersonalOAuthCallbackService, Depends(get_personal_oauth_callback_service)],
    return_destination: Annotated[str, Depends(get_personal_oauth_return_destination)],
) -> HTMLResponse:
    if re.fullmatch(r"[a-f0-9]{64}", issuer_key) is None:
        return callback_response(400, return_destination)
    return await finish_callback(request, service, IssuerRoute(kind="issuer", issuer_key=issuer_key), return_destination)


def canonical_callback_path(request: Request, route: CallbackRoute) -> bool:
    suffix = "/callback"
    if isinstance(route, IssuerRoute):
        suffix += "/issuer/" + route.issuer_key
    expected = request.scope.get("root_path", "").rstrip("/") + suffix
    return request.scope.get("raw_path", b"") == expected.encode("ascii")


async def finish_callback(
    request: Request, service: PersonalOAuthCallbackService, route: CallbackRoute, return_destination: str,
) -> HTMLResponse:
    parameters = getattr(request.state, CALLBACK_QUERY_KEY, {})
    if not parameters or not canonical_callback_path(request, route):
        return callback_response(400, return_destination)
    if isinstance(route, GenericRoute) and not parameters.get("iss"):
        return callback_response(400, return_destination)
    try:
        await service.finish(FinishCallback(
            state=SecretStr(parameters["state"]), code=SecretStr(parameters.get("code", "")),
            issuer=PresentCallbackIssuer(kind="present", value=parameters["iss"])
            if "iss" in parameters else MissingCallbackIssuer(kind="missing"),
            error=parameters.get("error", ""),
            scope=parameters.get("scope", ""), route=route,
        ))
    except Exception:
        return callback_response(400, return_destination)
    return callback_response(200, return_destination)
