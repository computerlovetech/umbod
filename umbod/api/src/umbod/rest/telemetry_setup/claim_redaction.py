from starlette._utils import get_route_path
from starlette.types import ASGIApp, Receive, Scope, Send

from umbod.rest.authentication.rest_paths import install_claim_redemption_request


class InstallClaimQueryRedactionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and (
            install_claim_redemption_request(scope)
            or (
                scope["method"] == "POST"
                and get_route_path(scope) == "/api/me/telemetry/install-claims"
            )
        ):
            scope["query_string"] = b""
        await self._app(scope, receive, send)
