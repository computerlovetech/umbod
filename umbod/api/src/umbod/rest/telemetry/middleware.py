from time import perf_counter
from typing import Literal, cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from umbod.core.signals import SignalPublisher
from umbod.rest.telemetry.observations import CompletedCollectorRequest

COLLECTOR_ROUTES = frozenset({"/v1/logs", "/v1/metrics", "/v1/traces"})
KNOWN_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})


class CollectorObservationsMiddleware:
    def __init__(
        self, app: ASGIApp, completed_requests: SignalPublisher[CompletedCollectorRequest],
    ) -> None:
        self.app = app
        self.completed_requests = completed_requests

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in COLLECTOR_ROUTES:
            await self.app(scope, receive, send)
            return
        route = cast(Literal["/v1/logs", "/v1/metrics", "/v1/traces"], scope["path"])
        method = scope["method"].upper()
        started_at = perf_counter()
        status_code = 500

        async def observe_response(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, observe_response)
        finally:
            self.completed_requests.send(CompletedCollectorRequest(
                method=method if method in KNOWN_METHODS else "OTHER",
                route=route, status_class=f"{status_code // 100}xx",
                duration_seconds=max(perf_counter() - started_at, 1e-12),
            ))
