import logging
from time import perf_counter
from typing import Optional, Sequence, cast

from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from umbod.rest.metrics.models import CompletedRestRequest
from umbod.rest.metrics.recorder import RestMetricsRecorder


logger = logging.getLogger(__name__)
KNOWN_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})


class AdminRestMetricsMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        recorder: RestMetricsRecorder,
        routes: Sequence[BaseRoute],
    ) -> None:
        self.app = app
        self.recorder = recorder
        self.routes = tuple(routes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        normalized_route = self._matched_route(scope)
        if normalized_route is None:
            await self.app(scope, receive, send)
            return
        started_at = perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = cast(int, message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            self._record_completed_request(scope, normalized_route, status_code, started_at)

    def _record_completed_request(
        self,
        scope: Scope,
        normalized_route: str,
        status_code: int,
        started_at: float,
    ) -> None:
        method = scope["method"].upper()
        bounded_method = method if method in KNOWN_METHODS else "OTHER"
        try:
            self.recorder.record_completed_request(
                CompletedRestRequest(
                    method=bounded_method,
                    normalized_route=normalized_route,
                    status_class=f"{status_code // 100}xx",
                    duration_seconds=max(perf_counter() - started_at, 1e-12),
                )
            )
        except Exception:
            logger.exception(
                "REST metrics recording failed",
                extra={
                    "method": bounded_method,
                    "normalized_route": normalized_route,
                    "status_code": status_code,
                },
            )

    def _matched_route(self, scope: Scope) -> Optional[str]:
        for route in self.routes:
            match, _ = route.matches(scope)
            if match in (Match.FULL, Match.PARTIAL):
                route_path = getattr(route, "path", None)
                if isinstance(route_path, str):
                    return f"/admin{route_path}"
        return None
